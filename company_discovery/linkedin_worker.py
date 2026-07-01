import os
import re
import json
import requests
from dotenv import load_dotenv
from tavily import TavilyClient

from models.schemas import SearchSpecification, RawEvidence
from company_vault.vault import CompanyVaultManager

load_dotenv()

"""
linkedin_worker.py

Independently discovers companies by searching LinkedIn company pages
(linkedin.com/company/...) using the search specification, then pulls
whatever public-facing information it can from each page and stores it
in the vault, arranged by section, plus the raw page text for later
business inference.

IMPORTANT CAVEAT (read before relying on this in production):
LinkedIn does not offer a public API for searching or reading arbitrary
company pages, and it actively blocks unauthenticated scraping of company
profiles (most pages redirect to a login wall for non-logged-in requests).
This worker is built to:
  1. Use Tavily (site-restricted to linkedin.com/company) to discover
     LinkedIn company page URLs and pull whatever snippet/preview text
     Tavily's crawler already captured — this part is reliable since
     Tavily does the fetching.
  2. Attempt a direct fetch of each page as a best-effort fallback to get
     more text. This will frequently fail or return a login wall, and the
     code accounts for that by just skipping it when it does.
For a production-grade version with reliable full-profile data (employee
count, follower growth, post history, etc.), you'd want LinkedIn's
official Marketing/Talent/Sales Navigator APIs (partner-gated) or a
licensed third-party data provider (e.g. Proxycurl, Bright Data) rather
than raw scraping. This implementation is structured so swapping in one
of those later only touches `_fetch_profile_page`.

Philosophy: this worker does NOT decide what is relevant. It collects as
much raw and lightly-structured information as it can per company and
stores all of it in the vault. Filtering / interpretation happens later,
downstream.
"""

# Recognizable section headers that tend to appear on LinkedIn company pages
SECTION_PATTERNS = {
    "overview": r"(Overview|About us)\s*[:\n](.*?)(?=\n[A-Z][a-z]+\s*[:\n]|$)",
    "industry": r"Industry\s*[:\n]?\s*(.+)",
    "company_size": r"Company size\s*[:\n]?\s*(.+)",
    "headquarters": r"Headquarters\s*[:\n]?\s*(.+)",
    "founded": r"Founded\s*[:\n]?\s*(.+)",
    "specialties": r"Specialties\s*[:\n]?\s*(.+)",
    "website": r"Website\s*[:\n]?\s*(.+)",
    "followers": r"([\d,.]+[KM]?)\s+followers",
    "employees_on_linkedin": r"([\d,.]+[KM]?)\s+employees on LinkedIn",
}


class LinkedInWorker:
    def __init__(self):
        self.tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    def discover(self, search_spec: SearchSpecification, vault: CompanyVaultManager):
        """
        Independently finds companies via LinkedIn and stores everything
        found about each one in the vault.
        """
        query = self._build_search_query(search_spec)
        linkedin_results = self._search_linkedin(query)

        print(f"LinkedIn worker found {len(linkedin_results)} candidate pages.")

        for result in linkedin_results:
            url = result.get("url", "")
            if "linkedin.com/company" not in url:
                continue

            company_name = self._extract_company_name(result)
            if not company_name:
                continue

            vault.add_company(company_name)

            # Evidence #1: whatever Tavily already crawled (reliable)
            tavily_snippet = result.get("content", "")
            if tavily_snippet:
                vault.add_evidence(
                    company_name,
                    RawEvidence(
                        source="LinkedInWorker",
                        source_type="linkedin",
                        url=url,
                        title="LinkedIn Search Snippet",
                        metadata={"section": "raw_snippet"},
                        content=tavily_snippet,
                        confidence=0.6,
                    ),
                )

                # Pull out structured fields we can recognize from the snippet
                structured = self._extract_structured_fields(tavily_snippet)
                for field_name, field_value in structured.items():
                    vault.add_evidence(
                        company_name,
                        RawEvidence(
                            source="LinkedInWorker",
                            source_type="linkedin",
                            url=url,
                            title=field_name.replace("_", " ").title(),
                            metadata={"section": field_name},
                            content=field_value,
                            confidence=0.7,
                        ),
                    )

            # Evidence 2: best-effort direct fetch of the page itself
            page_text = self._fetch_profile_page(url)
            if page_text:
                vault.add_evidence(
                    company_name,
                    RawEvidence(
                        source="LinkedInWorker",
                        source_type="linkedin",
                        url=url,
                        title="LinkedIn Page (direct fetch)",
                        metadata={"section": "raw_page"},
                        content=page_text,
                        confidence=0.5,
                    ),
                )

                structured = self._extract_structured_fields(page_text)
                for field_name, field_value in structured.items():
                    vault.add_evidence(
                        company_name,
                        RawEvidence(
                            source="LinkedInWorker",
                            source_type="linkedin",
                            url=url,
                            title=field_name.replace("_", " ").title(),
                            metadata={"section": field_name},
                            content=field_value,
                            confidence=0.7,
                        ),
                    )

            # Evidence3: Company updates / posts, if discoverable, for
            # later sentiment / activity-based business inference.
            posts = self._search_linkedin_posts(company_name)
            for post in posts:
                vault.add_evidence(
                    company_name,
                    RawEvidence(
                        source="LinkedInWorker",
                        source_type="linkedin",
                        url=post.get("url", ""),
                        title="LinkedIn Activity / Post",
                        metadata={"section": "activity"},
                        content=post.get("content", ""),
                        confidence=0.4,
                    ),
                )

    # ------------------------------------------------------------------
    # Query building
    # ------------------------------------------------------------------
    def _build_search_query(self, search_spec: SearchSpecification) -> str:
        query_parts = [search_spec.objective, "site:linkedin.com/company"]
        for value in search_spec.constraints.values():
            query_parts.append(value)
        return " ".join(query_parts)

    # ------------------------------------------------------------------
    # Discovery search
    # ------------------------------------------------------------------
    def _search_linkedin(self, query: str):
        try:
            response = self.tavily.search(
                query=query,
                search_depth="advanced",
                max_results=20,
                include_domains=["linkedin.com"],
            )
            return response.get("results", [])
        except Exception as e:
            print(f"LinkedIn search error: {e}")
            return []

    def _search_linkedin_posts(self, company_name: str):
        try:
            response = self.tavily.search(
                query=f"{company_name} site:linkedin.com/posts OR site:linkedin.com/company {company_name} updates",
                search_depth="basic",
                max_results=5,
                include_domains=["linkedin.com"],
            )
            return response.get("results", [])
        except Exception as e:
            print(f"LinkedIn posts search error for {company_name}: {e}")
            return []

    # ------------------------------------------------------------------
    # Name extraction
    # ------------------------------------------------------------------
    def _extract_company_name(self, result: dict) -> str | None:
        """
        Derives a company name from a LinkedIn search result, preferring
        the page title (cleaned of LinkedIn's standard suffixes) and
        falling back to the URL slug.
        """
        title = result.get("title", "")
        if title:
            name = re.split(r"[\|\-–]\s*LinkedIn", title)[0].strip()
            if name:
                return name

        url = result.get("url", "")
        match = re.search(r"linkedin\.com/company/([^/?]+)", url)
        if match:
            slug = match.group(1)
            return slug.replace("-", " ").title()

        return None

    # ------------------------------------------------------------------
    # Direct page fetch (best effort, frequently blocked)
    # ------------------------------------------------------------------
    def _fetch_profile_page(self, url: str) -> str | None:
        try:
            response = requests.get(
                url,
                timeout=10,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"
                    )
                },
            )

            if response.status_code != 200:
                return None

            text = response.text

            # LinkedIn redirects logged-out requests to an auth wall; bail
            # out if that's clearly what we got rather than storing junk.
            if "authwall" in response.url or "Join LinkedIn" in text[:2000]:
                return None

            import trafilatura
            extracted = trafilatura.extract(text)
            return extracted
        except Exception as e:
            print(f"Could not fetch LinkedIn page {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Structured field extraction from whatever text we have
    # ------------------------------------------------------------------
    def _extract_structured_fields(self, text: str) -> dict:
        """
        Best-effort regex extraction of recognizable LinkedIn profile
        fields (industry, company size, HQ, founded, specialties, etc.)
        from raw page or snippet text. Returns only fields it actually
        found — nothing is invented.
        """
        fields = {}
        for field_name, pattern in SECTION_PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                if value:
                    fields[field_name] = value[:1000]  # keep it sane
        return fields


if __name__ == "__main__":
    search_spec = SearchSpecification(
        intent="Company Discovery",
        objective="Find companies that need AI solutions",
        constraints={"region": "South Africa"},
        required_attributes=[],
        clarification_required=False,
        missing_information=[],
        clarification_questions=[],
        confidence=0.95,
    )

    vault = CompanyVaultManager()
    worker = LinkedInWorker()
    worker.discover(search_spec, vault)

    for company in vault.get_all_companies():
        print("\n" + "=" * 80)
        print(f"Company: {company.identity.name}")
        for evidence in company.raw_evidence:
            print(f"--- {evidence.title} ({evidence.metadata.get('section')}) ---")
            print(evidence.content[:300])
        print("=" * 80)