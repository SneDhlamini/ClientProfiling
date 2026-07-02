from prompt.prompt import llm
from models.schemas import SearchSpecification, RawEvidence, CompanyProfile, CompanyIdentity
from company_vault.vault import CompanyVaultManager

import requests
import trafilatura
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import os
from dotenv import load_dotenv
from tavily import TavilyClient

# Section pages we try to find and read for each company, beyond the homepage.
SECTION_KEYWORDS = ["about", "contact", "careers", "products", "services"]

# Domains that are never the "official website" - they're social/profile
# pages or data aggregators, not a company's own site. LinkedIn especially
# is already handled by LinkedInWorker, so WebWorker should skip past it
# rather than resolve "official website" to a LinkedIn company page.
EXCLUDED_WEBSITE_DOMAINS = [
    "linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "zoominfo.com", "leadiq.com", "globaldata.com", "wikipedia.org",
]

# How many companies to process at once, and how many page-fetches per
# company to run at once. Total concurrent network calls is roughly the
# product of the two - keep it moderate to avoid tripping Tavily or
# individual company sites' rate limits.
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

        # Process companies concurrently instead of one at a time - this is
        # the single biggest speedup, since each company's work is almost
        # entirely waiting on network I/O.
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
            print(f"Could not resolve website for {company_name}, skipping.")
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

    # ------------------------------------------------------------------
    # Company name extraction (LLM-based, from Tavily article results)
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Official website resolution (one Tavily search per company)
    # ------------------------------------------------------------------
    def _find_company_website(self, company_name: str) -> str | None:
        try:
            response = self.tavily.search(
                query=f"{company_name} official website",
                search_depth="basic",
                max_results=5,
            )
            results = response.get("results", [])
            for result in results:
                url = result.get("url", "")
                if not url:
                    continue
                if any(domain in url.lower() for domain in EXCLUDED_WEBSITE_DOMAINS):
                    continue
                return url
            return None
        except Exception as e:
            print(f"Could not resolve website for {company_name}: {e}")
            return None

    # ------------------------------------------------------------------
    # Evidence collection: homepage + section pages (about, contact, etc.)
    # Fetched concurrently instead of one at a time.
    # ------------------------------------------------------------------
    def _collect_company_evidence(
        self,
        company_name: str,
        website: str,
        vault: CompanyVaultManager,
    ):
        tasks = [("home", website)]
        tasks += [(section, None) for section in SECTION_KEYWORDS]

        with ThreadPoolExecutor(max_workers=MAX_PAGE_WORKERS) as executor:
            futures = {}
            for section, known_url in tasks:
                futures[executor.submit(
                    self._fetch_section, company_name, website, section, known_url
                )] = section

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
                        title=section.capitalize() if section != "home" else "Home",
                        metadata={"section": section},
                        content=content,
                    ),
                )

    def _fetch_section(self, company_name, website, section, known_url):
        """
        Resolves the URL for one section (if not already known, i.e. the
        homepage) and reads it. Returns (url, content) or None if nothing
        usable was found. Designed to be run inside a thread pool.
        """
        url = known_url or self._find_section_url(website, company_name, section)
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

    # ------------------------------------------------------------------
    # Page reading - direct fetch + trafilatura extraction.
    #
    # No third-party reader/proxy service involved (previously used Jina
    # Reader, which shares its rate limit across everyone using it
    # unauthenticated, and outright refuses certain domains like LinkedIn
    # with HTTP 451). Reading pages ourselves means the only limits we
    # hit are each individual site's own, which is far more predictable.
    # ------------------------------------------------------------------
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


# testing
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
            print(f"--- {evidence.title} ({evidence.url}) ---")
            print(evidence.content)
        print("=" * 80)