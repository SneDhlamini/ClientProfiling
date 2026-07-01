import os
import re
import json
import requests
from dotenv import load_dotenv
from tavily import TavilyClient

from models.schemas import SearchSpecification, RawEvidence
from company_vault.vault import CompanyVaultManager

load_dotenv()



COMPANY_URL_PATTERN = re.compile(r"linkedin\.com/company/([^/?#]+)", re.IGNORECASE)
PROFILE_URL_PATTERN = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)

# Known headers that can follow any field on a LinkedIn page/snippet.
# Used as a stopping boundary so a field's regex doesn't swallow the next
# section's text.
_NEXT_HEADER = (
    r"(?=\n#{0,3}\s*(?:Crunchbase|LinkedIn|Industry|Company size|Type|"
    r"Headquarters|Founded|Funding|Investors|Specialties|Website|Locations|"
    r"Employees|Overview|About us)\b|\Z)"
)

SECTION_PATTERNS = {
    "overview": r"(?:Overview|About us)\s*[:\n]\s*(.*?)" + _NEXT_HEADER,
    "industry": r"Industry\s*[:\n]\s*(.*?)" + _NEXT_HEADER,
    "company_size": r"Company size\s*[:\n]\s*([\d,]+[\s\-–]*[\d,]*\+?\s*employees)",
    "headquarters": r"Headquarters\s*[:\n]\s*(.*?)" + _NEXT_HEADER,
    "founded": r"Founded\s*[:\n]\s*(\d{4})",
    "specialties": r"Specialties\s*[:\n]\s*(.*?)" + _NEXT_HEADER,
    "website": r"Website\s*[:\n]\s*(.*?)" + _NEXT_HEADER,
    "followers": r"([\d,.]+[KM]?)\s+followers",
    "employees_on_linkedin": r"([\d,.]+[KM]?)\s+employees on LinkedIn",
}


class LinkedInWorker:
    def __init__(self):
        self.tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    def discover(self, search_spec: SearchSpecification, vault: CompanyVaultManager):
        company_pages = self._search_company_pages(search_spec)
        print(f"LinkedIn worker found {len(company_pages)} company page candidates.")

        seen_names = set()

        for result in company_pages:
            url = result.get("url", "")
            company_name = self._extract_company_name(result)
            if not company_name or company_name.lower() in seen_names:
                continue
            seen_names.add(company_name.lower())

            vault.add_company(company_name)
            print(f"  -> {company_name} ({url})")

            snippet_text = result.get("content", "")
            page_text = self._fetch_profile_page(url)

            # Store the two raw blobs once each (full context, for anything
            # the structured extraction misses).
            if snippet_text:
                vault.add_evidence(
                    company_name,
                    RawEvidence(
                        source="LinkedInWorker", source_type="linkedin", url=url,
                        title="LinkedIn Search Snippet",
                        metadata={"section": "raw_snippet"},
                        content=snippet_text, confidence=0.6,
                    ),
                )
            if page_text:
                vault.add_evidence(
                    company_name,
                    RawEvidence(
                        source="LinkedInWorker", source_type="linkedin", url=url,
                        title="LinkedIn Page (direct fetch)",
                        metadata={"section": "raw_page"},
                        content=page_text, confidence=0.5,
                    ),
                )

            # Merge structured fields from both sources, page text wins
            # ties since it's the more complete fetch; store each field
            # exactly once per company, in a fixed, readable order.
            merged_fields = {}
            merged_fields.update(self._extract_structured_fields(snippet_text))
            merged_fields.update(self._extract_structured_fields(page_text or ""))

            field_order = ["industry", "company_size", "headquarters", "founded",
                           "specialties", "website", "followers",
                           "employees_on_linkedin", "overview"]
            for field_name in field_order:
                if field_name in merged_fields:
                    vault.add_evidence(
                        company_name,
                        RawEvidence(
                            source="LinkedInWorker", source_type="linkedin", url=url,
                            title=field_name.replace("_", " ").title(),
                            metadata={"section": field_name},
                            content=merged_fields[field_name], confidence=0.7,
                        ),
                    )

            for contact in self._search_sales_team(company_name):
                vault.add_evidence(
                    company_name,
                    RawEvidence(
                        source="LinkedInWorker",
                        source_type="linkedin",
                        url=contact["url"],
                        title="Sales Team Contact",
                        metadata={"section": "sales_contact", "name": contact["name"], "title": contact["job_title"]},
                        content=f"Name: {contact['name']}\nTitle: {contact['job_title']}\nProfile: {contact['url']}",
                        confidence=0.5,
                    ),
                )

            for post in self._search_company_activity(company_name):
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
    # Discovery search: a few angles, since one query often misses
    # ------------------------------------------------------------------
    def _search_company_pages(self, search_spec: SearchSpecification):
        # Prefer the richer, purpose-written discovery_prompt from prompt.py;
        # fall back to objective + constraints if it wasn't set.
        text_query = search_spec.discovery_prompt or search_spec.objective
        constraint_terms = " ".join(search_spec.constraints.values())

        queries = [
            f'{text_query} {constraint_terms} linkedin company',
            f'{text_query} {constraint_terms} "linkedin.com/company"',
        ]

        all_results = []
        seen_urls = set()

        for query in queries:
            try:
                response = self.tavily.search(
                    query=query,
                    search_depth="advanced",
                    max_results=15,
                    include_domains=["linkedin.com"],
                )
                for result in response.get("results", []):
                    url = result.get("url", "")
                    if not COMPANY_URL_PATTERN.search(url):
                        continue
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    all_results.append(result)
            except Exception as e:
                print(f"LinkedIn company page search error: {e}")

        return all_results

    def _search_sales_team(self, company_name: str):
        """
        Finds people with sales-related titles at the company via
        site-restricted search of LinkedIn profile pages. Returns name,
        job title, and profile URL only — no emails/phone numbers, since
        LinkedIn does not expose those publicly.
        """
        contacts = []
        sales_word = re.compile(r"\bsales\b", re.IGNORECASE)
        # Platform/product names that contain "sales" as a substring but
        # are not job titles (e.g. "Salesforce") — excluded explicitly.
        false_positive_titles = {"salesforce"}

        try:
            response = self.tavily.search(
                query=f'"{company_name}" sales linkedin profile',
                search_depth="basic",
                max_results=10,
                include_domains=["linkedin.com"],
            )
            for result in response.get("results", []):
                url = result.get("url", "")
                if not PROFILE_URL_PATTERN.search(url):
                    continue

                title = result.get("title", "")
                content = result.get("content", "")

                # Require the company to actually be mentioned in this
                # profile's title or content, not just a coincidental hit.
                if company_name.lower() not in (title + " " + content).lower():
                    continue

                # LinkedIn profile titles are typically "Name - Job Title - Company | LinkedIn"
                parts = re.split(r"\s*[\|\-–]\s*", title)
                parts = [p.strip() for p in parts if p.strip() and p.strip().lower() != "linkedin"]

                if not parts:
                    continue

                name = parts[0]
                job_title = parts[1] if len(parts) > 1 else ""

                if job_title.strip().lower() in false_positive_titles:
                    continue
                if not sales_word.search(job_title) and not sales_word.search(content):
                    continue

                contacts.append({"name": name, "job_title": job_title, "url": url})
        except Exception as e:
            print(f"LinkedIn sales team search error for {company_name}: {e}")

        return contacts

    def _search_company_activity(self, company_name: str):
        try:
            response = self.tavily.search(
                query=f'"{company_name}" updates announcement linkedin',
                search_depth="basic",
                max_results=5,
                include_domains=["linkedin.com"],
            )
            results = response.get("results", [])
            # Keep only results that actually mention the company, so we
            # don't store unrelated people's profiles as "activity".
            return [
                r for r in results
                if company_name.lower() in (r.get("title", "") + " " + r.get("content", "")).lower()
            ]
        except Exception as e:
            print(f"LinkedIn activity search error for {company_name}: {e}")
            return []

    # ------------------------------------------------------------------
    # Name extraction
    # ------------------------------------------------------------------
    def _extract_company_name(self, result: dict) -> str | None:
        title = result.get("title", "")
        if title:
            name = re.split(r"[\|\-–]\s*LinkedIn", title)[0].strip()
            if name:
                return name

        url = result.get("url", "")
        match = COMPANY_URL_PATTERN.search(url)
        if match:
            return match.group(1).replace("-", " ").title()

        return None

    # ------------------------------------------------------------------
    # Direct page fetch (best effort, frequently blocked by login wall)
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
            if "authwall" in response.url or "Join LinkedIn" in text[:2000]:
                return None

            import trafilatura
            return trafilatura.extract(text)
        except Exception as e:
            print(f"Could not fetch LinkedIn page {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Structured field extraction from whatever text we have
    # ------------------------------------------------------------------
    def _extract_structured_fields(self, text: str) -> dict:
        fields = {}
        for field_name, pattern in SECTION_PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                if value:
                    fields[field_name] = value[:1000]
        return fields


def print_company_report(vault: CompanyVaultManager):
    """
    Prints one clean, ordered block per company: core profile fields
    first in a fixed order, then sales contacts, then activity, then a
    note about the raw evidence available for downstream inference.
    Each company's full block prints before moving to the next company.
    """
    field_order = ["industry", "company_size", "headquarters", "founded",
                   "specialties", "website", "followers",
                   "employees_on_linkedin", "overview"]

    for company in vault.get_all_companies():
        by_section = {}
        sales_contacts = []
        activity = []
        raw_count = 0

        for evidence in company.raw_evidence:
            section = evidence.metadata.get("section", "")
            if section in field_order:
                by_section[section] = evidence.content
            elif section == "sales_contact":
                sales_contacts.append(evidence)
            elif section == "activity":
                activity.append(evidence)
            else:
                raw_count += 1

        print("\n" + "=" * 80)
        print(f"COMPANY: {company.identity.name}")
        print("=" * 80)

        for field in field_order:
            if field in by_section:
                label = field.replace("_", " ").title()
                print(f"{label:>22}: {by_section[field][:200]}")

        if sales_contacts:
            print("\nSales Team Contacts:")
            for c in sales_contacts:
                print(f"  - {c.metadata.get('name')} | {c.metadata.get('title')} | {c.url}")

        if activity:
            print("\nRecent Activity:")
            for a in activity:
                print(f"  - {a.content[:150].strip()}...")

        if raw_count:
            print(f"\n({raw_count} additional raw evidence record(s) stored for downstream inference)")


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

    print_company_report(vault)