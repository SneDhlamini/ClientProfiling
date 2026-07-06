from prompt.prompt import llm
from models.schemas import SearchSpecification, RawEvidence, CompanyProfile, CompanyIdentity
from company_vault.vault import CompanyVaultManager

import requests
import trafilatura
import time
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import os
from dotenv import load_dotenv
from tavily import TavilyClient

# Section pages beyond the homepage.
SECTION_KEYWORDS = ["about",
                    "about-us",
                     "contact",
                     "contact-us",
                     "careers", 
                     "products", 
                     "services",
                     "solutions",
                     ]

# To catch cases where the url isnt actually an official website
NEVER_OFFICIAL_DOMAINS = [
    "linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "zoominfo.com", "leadiq.com", "globaldata.com", "wikipedia.org",
    "crunchbase.com", "owler.com", "dnb.com", "bloomberg.com", "craft.co",
    "rocketreach.co", "apollo.io", "weforum.org", "africanfinancials.com",
    "jimdosite.com", "wixsite.com", "weebly.com", "blogspot.com",
    "wordpress.com", "squarespace.com", "godaddysites.com",
    "sites.google.com", "medium.com",
]

# stop deduplication:Legal-entity suffix words stripped out

COMPANY_SUFFIX_WORDS = {
    "inc", "incorporated", "ltd", "limited", "llc", "plc", "corp",
    "corporation", "co", "company", "group", "holdings", "international",
    "industries", "enterprises", "gmbh", "sa", "ag", "kg",
}

# Minimum name/domain token overlap (0.0-1.0) to accept a candidate as
# plausibly the company's own site, rather than a third party that just
# happens to mention them.
MIN_NAME_SIMILARITY = 0.3

# How many companies to process at once, and how many page-fetches per company. Too many concurrent fetches can trigger anti-bot measures
MAX_COMPANY_WORKERS = 5
MAX_PAGE_WORKERS = 6

READ_MAX_ATTEMPTS = 2

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

load_dotenv()


class WebWorker:
    def __init__(self):
        self.llm = llm
        self.tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    def discover(
        self,
        search_spec: SearchSpecification,
        vault: CompanyVaultManager
    ):
        start = time.time()

        query = self._build_search_query(search_spec)
        results = self._search_web(query)
        companies = self.extract_candidate_companies(results, search_spec)
        print(f"Web worker extracted {len(companies)} candidate companies: {companies}")

        # Process companies concurrently instead of one at a time 
        
        with ThreadPoolExecutor(max_workers=MAX_COMPANY_WORKERS) as executor:
            futures = {
                executor.submit(self._process_company, name, vault): name
                for name in companies
            }
            for future in as_completed(futures):
                company_name = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"Error processing {company_name}: {e}")

        print(f"Web worker finished in {time.time() - start:.1f}s")

    def _process_company(self, company_name: str, vault: CompanyVaultManager):
        website = self._find_company_website(company_name)
        if not website:
            print(f"Could not resolve a valid website for {company_name}, skipping.")
            return

        print(f"  -> {company_name} ({website})")

        vault.add_company(company_name)
        vault.get_company(company_name).identity.website = website

        self._collect_company_evidence(company_name, website, vault)

    def _build_search_query(
        self,
        search_spec: SearchSpecification
    ) -> str:
        query_parts = [search_spec.objective]
        for value in search_spec.constraints.values():
            query_parts.append(value)
        return " ".join(query_parts)

    def _search_web(self, query: str):
        response = self.tavily.search(
            query=query,
            search_depth="advanced",
            max_results=5,
        )
        return response.get("results", [])

    
    # Company name extraction (LLM-based, from Tavily article results)
    
    def extract_candidate_companies(self, results, search_spec: SearchSpecification):
        """
        Uses the LLM to extract actual company names from Tavily search results.
        """
        search_text = ""
        for result in results:
            title = result.get("title", "")
            content = result.get("content", "")

            search_text += f"""
Title:
{title}

Content:
{content}
------------------------------------------------------
"""

        prompt = f"""
You are a business intelligence analyst.
Below are search results collected from the web.
Your task is not to summarize them.
Instead, identify every REAL COMPANY mentioned.

Rules:
- Return only company names, one per line.
- Ignore articles.
- Ignore websites that are NOT companies.
- Remove duplicates.
- If no companies exist, return an empty list.

Search Results:
{search_text}
"""
        response = self.llm.invoke(prompt)

        companies = [
            company.replace("•", "").replace("-", "").strip()
            for company in response.content.split("\n")
            if company.strip()
        ]
        return companies

    # Official website resolution
    # No extra
    # Tavily calls - same single search as before, just used better.
    def _find_company_website(self, company_name: str) -> str | None:
        try:
            response = self.tavily.search(
                query=f"{company_name} official website",
                search_depth="basic",
                max_results=5,
            )
            results = response.get("results", [])
        except Exception as e:
            print(f"Could not resolve website for {company_name}: {e}")
            return None

        name_tokens = self._normalize_name_tokens(company_name)
        acronym = self._extract_acronym(company_name)
        candidates = []

        for result in results:
            url = result.get("url", "")
            if not url:
                continue

            domain = self._get_domain(url)
            if any(blocked in domain for blocked in NEVER_OFFICIAL_DOMAINS):
                continue

            label = self._domain_label(url)

            # Exact/near-exact acronym match  is
            # a very strong signal even when the full name barely
            # overlaps with the domain - treat it as a top candidate.
            if acronym and (label == acronym or label.startswith(acronym)):
                similarity = 1.0
            else:
                matched = sum(1 for token in name_tokens if token in label)
                similarity = matched / max(len(name_tokens), 1)

            candidates.append((similarity, url))

        # Highest name-similarity first; original Tavily order preserved
        # as a tiebreaker since candidates were appended in that order.
        candidates.sort(key=lambda c: c[0], reverse=True)

        for similarity, url in candidates:
            if similarity < MIN_NAME_SIMILARITY:
                continue
            if self._domain_is_reachable(url):
                return url

        return None

    def _normalize_name_tokens(self, name: str) -> set[str]:
        words = re.findall(r"[a-zA-Z]+", name.lower())
        return {w for w in words if w not in COMPANY_SUFFIX_WORDS and len(w) > 1}

    def _extract_acronym(self, name: str) -> str | None:
        """
        Pulls a parenthetical acronym out of a company name.
        """
        match = re.search(r"\(([A-Za-z]{2,6})\)", name)
        return match.group(1).lower() if match else None

    def _domain_label(self, url: str) -> str:
        """
        Returns the registrable domain's first label with all
        non-letter characters stripped, e.g. "dangote-cement.jimdosite.com"
        -> "dangotecement". Stripping hyphens/digits means both
        hyphenated and concatenated domain naming styles (tigerbrands.com
        vs dangote-cement.com) are matched the same way, via substring
        containment rather than exact token equality.
        """
        try:
            netloc = urlparse(url).netloc.lower().replace("www.", "")
            label = netloc.split(".")[0]
            return re.sub(r"[^a-z]", "", label)
        except Exception:
            return ""

    def _get_domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    def _domain_is_reachable(self, url: str) -> bool:
        try:
            resp = requests.head(url, timeout=5, allow_redirects=True, headers=BROWSER_HEADERS)
            return resp.status_code < 400
        except Exception:
            try:
                # Some sites reject HEAD requests outright - fall back to
                # a light GET rather than discarding a real candidate.
                resp = requests.get(url, timeout=6, headers=BROWSER_HEADERS, stream=True)
                resp.close()
                return resp.status_code < 400
            except Exception:
                return False

    # ------------------------------------------------------------------
    # Evidence collection: homepage first (synchronously, so we can
    # verify it and compute a confidence score before anything else),
    # then section pages (about, contact, etc.) concurrently.
    # ------------------------------------------------------------------
    def _collect_company_evidence(
        self,
        company_name: str,
        website: str,
        vault: CompanyVaultManager,
    ):
        home_content = self.read_page(website)
        if not home_content:
            print(f"Could not read homepage for {company_name} ({website}), skipping.")
            return

        confidence = self._verify_official_match(company_name, home_content)
        if confidence < 0.5:
            print(
                f"  Warning: homepage for {company_name} ({website}) doesn't clearly "
                f"mention the company name - keeping evidence at reduced confidence ({confidence})."
            )

        vault.add_evidence(
            company_name,
            RawEvidence(
                source="WebWorker",
                source_type="website",
                url=website,
                title="Home",
                metadata={"section": "home"},
                content=home_content,
                confidence=confidence,
            ),
        )

        with ThreadPoolExecutor(max_workers=MAX_PAGE_WORKERS) as executor:
            futures = {
                executor.submit(self._fetch_section, company_name, website, section): section
                for section in SECTION_KEYWORDS
            }

            for future in as_completed(futures):
                section = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    print(f"Error fetching {section} for {company_name}: {e}")
                    continue

                if result is None:
                    continue

                section_url, content = result
                vault.add_evidence(
                    company_name,
                    RawEvidence(
                        source="WebWorker",
                        source_type="website",
                        url=section_url,
                        title=section.capitalize(),
                        metadata={"section": section},
                        content=content,
                        confidence=confidence,
                    ),
                )

    def _verify_official_match(self, company_name: str, page_text: str) -> float:
        """
        Loose check that the fetched homepage is actually about this
        company, since even a reachable, name-similar domain could
        still be wrong. Doesn't discard the evidence either way.
        """
        name_tokens = self._normalize_name_tokens(company_name)
        if not name_tokens:
            return 0.7

        text_lower = page_text[:3000].lower()
        matched = sum(1 for token in name_tokens if token in text_lower)
        ratio = matched / len(name_tokens)

        if ratio >= 0.5:
            return 1.0
        elif ratio > 0:
            return 0.6
        else:
            return 0.3

    def _fetch_section(self, company_name, website, section):
        """
        Resolves the URL for one section and reads it. Returns
        (url, content) or None if nothing usable was found. Designed to
        be run inside a thread pool.
        """
        url = self._find_section_url(website, company_name, section)
        if not url:
            return None

        content = self.read_page(url)
        if not content:
            return None

        return url, content

    def _find_section_url(self, website: str, company_name: str, section: str) -> str | None:
        """
        Tries common URL patterns concurrently first (fast, no API call),
        then falls back to a site-restricted Tavily search for the page.
        """
        domain = website.rstrip("/")
        guesses = [f"{domain}/{section}", f"{domain}/{section}-us", f"{domain}/{section}.html"]

        with ThreadPoolExecutor(max_workers=len(guesses)) as executor:
            futures = [executor.submit(self._head_ok, guess) for guess in guesses]
            for future, guess in zip(futures, guesses):
                if future.result():
                    return guess

        try:
            clean_domain = domain.replace("https://", "").replace("http://", "")
            response = self.tavily.search(
                query=f"{company_name} {section} site:{clean_domain}",
                search_depth="basic",
                max_results=1,
            )
            results = response.get("results", [])
            if results:
                return results[0].get("url")
        except Exception as e:
            print(f"Could not find {section} page for {company_name}: {e}")

        return None

    def _head_ok(self, url: str) -> bool:
        try:
            resp = requests.head(
                url, timeout=4, allow_redirects=True,
                headers=BROWSER_HEADERS,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # Page reading:direct fetch + trafilatura extraction.

    def read_page(self, url: str) -> str | None:
        for attempt in range(1, READ_MAX_ATTEMPTS + 1):
            try:
                response = requests.get(url, timeout=15, headers=BROWSER_HEADERS)

                if response.status_code != 200:
                    print(f"Could not read {url}: HTTP {response.status_code}")
                    return None

                extracted = trafilatura.extract(response.text)
                return extracted

            except requests.exceptions.RequestException as e:
                if attempt == READ_MAX_ATTEMPTS:
                    print(f"Could not read {url}: {e}")
                    return None
                time.sleep(1.0)

        return None


# testinggggg
if __name__ == "__main__":

    search_spec = SearchSpecification(
        intent="Company Discovery",
        objective="Find companies that need AI solutions",
        constraints={
            "region": "South Africa"
        },
        required_attributes=[],
        clarification_required=False,
        missing_information=[],
        clarification_questions=[],
        confidence=0.95
    )

    vault = CompanyVaultManager()
    worker = WebWorker()
    worker.discover(search_spec, vault)

    for company in vault.get_all_companies():
        print("\n" + "=" * 80)
        print(f"Company: {company.identity.name}")
        print(f"Website: {company.identity.website}")
        print("\nContent:")
        for evidence in company.raw_evidence:
            print(f"--- {evidence.title} ({evidence.url}) [confidence: {evidence.confidence}] ---")
            print(evidence.content)
        print("=" * 80)