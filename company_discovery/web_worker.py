from prompt.prompt import llm
from models.schemas import SearchSpecification, RawEvidence
from company_vault.vault import CompanyVaultManager

import requests
import trafilatura

import os
from dotenv import load_dotenv
from tavily import TavilyClient

# Pages we try to find and store for each company, beyond the homepage.
SECTION_KEYWORDS = ["about", "careers", "jobs", "products", "services"]

load_dotenv()


class WebWorker:
    def __init__(self):
        self.llm = llm
        self.tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    def discover(self, search_spec: SearchSpecification, vault: CompanyVaultManager):
        query = self._build_search_query(search_spec)
        results = self._search_web(query)
        companies = self.extract_candidate_companies(results, search_spec)

        for company_name in companies:
            website = self._find_company_website(company_name)
            if not website:
                print(f"Could not resolve website for {company_name}, skipping.")
                continue

            vault.add_company(company_name)
            vault.get_company(company_name).identity.website = website

            self._collect_company_evidence(company_name, website, vault)

    def _build_search_query(self, search_spec: SearchSpecification) -> str:
        # discovery_prompt (built by prompt.py) is the richer, purpose-written
        # query - use it when present, fall back to objective + constraints
        # for specs built without it (e.g. hand-built specs, tests).
        if search_spec.discovery_prompt:
            return search_spec.discovery_prompt

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

    def _find_company_website(self, company_name: str) -> str | None:
        """
        Uses Tavily to resolve a company's official website URL.
        """
        try:
            response = self.tavily.search(
                query=f"{company_name} official website",
                search_depth="basic",
                max_results=3,
            )
            results = response.get("results", [])
            if not results:
                return None
            return results[0].get("url")
        except Exception as e:
            print(f"Could not resolve website for {company_name}: {e}")
            return None

    def _collect_company_evidence(
        self,
        company_name: str,
        website: str,
        vault: CompanyVaultManager,
    ):
        """
        Visits the homepage plus likely section pages (about, careers, etc.)
        for a company and stores each as labelled evidence in the vault.
        """
        # Homepage
        home_content = self.read_page(website)
        if home_content:
            vault.add_evidence(
                company_name,
                RawEvidence(
                    source="WebWorker",
                    source_type="website",
                    url=website,
                    title="Home",
                    metadata={"section": "home"},
                    content=home_content,
                ),
            )

        # Try to discover section page links by searching site-restricted queries
        for section in SECTION_KEYWORDS:
            section_url = self._find_section_url(website, company_name, section)
            if not section_url:
                continue

            section_content = self.read_page(section_url)
            if not section_content:
                continue

            vault.add_evidence(
                company_name,
                RawEvidence(
                    source="WebWorker",
                    source_type="website",
                    url=section_url,
                    title=section.capitalize(),
                    metadata={"section": section},
                    content=section_content,
                ),
            )

    def _find_section_url(self, website: str, company_name: str, section: str) -> str | None:
        """
        Tries to find a specific section page (about/careers/etc.) for a company,
        first by guessing common URL patterns, then falling back to a search.
        """
        domain = website.rstrip("/")
        guesses = [f"{domain}/{section}", f"{domain}/{section}-us", f"{domain}/{section}.html"]

        for guess in guesses:
            try:
                resp = requests.head(guess, timeout=5, allow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    return guess
            except Exception:
                continue

        # Fallback: search for the section page
        try:
            response = self.tavily.search(
                query=f"{company_name} {section} site:{domain.replace('https://', '').replace('http://', '')}",
                search_depth="basic",
                max_results=1,
            )
            results = response.get("results", [])
            if results:
                return results[0].get("url")
        except Exception as e:
            print(f"Could not find {section} page for {company_name}: {e}")

        return None

    def read_page(self, url: str) -> str | None:
        """
        Download a webpage and extract the readable text.
        """
        try:
            response = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if response.status_code != 200:
                return None

            extracted = trafilatura.extract(response.text)
            return extracted
        except Exception as e:
            print(f"Could not read {url}: {e}")
            return None


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