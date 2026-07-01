import os
import json
import requests
from dotenv import load_dotenv

from models.schemas import SearchSpecification, RawEvidence
from company_vault.vault import CompanyVaultManager

load_dotenv()

"""
API_worker.py

This worker is fully independent of WebWorker. It does not read anything
from the vault, and it does not depend on company names found elsewhere.
It builds its own search criteria directly from the SearchSpecification and
uses company-discovery / screener endpoints on each API to find as many
companies as possible on its own.

Once it has a company name (discovered through an API, not handed to it),
it also pulls whatever additional financial / registry / firmographic data
that API can offer for that company, and stores everything as raw evidence.

Philosophy: this worker does NOT decide what is relevant. Every company
name found and every record returned is collected and stored as-is.
Filtering / interpretation happens later, downstream.
"""


class APIWorker:
    def __init__(self):
        self.opencorporates_key = os.getenv("OPENCORPORATES_API_KEY")
        self.fmp_key = os.getenv("FMP_API_KEY")  # Financial Modeling Prep
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        self.clearbit_key = os.getenv("CLEARBIT_API_KEY")

    def discover(self, search_spec: SearchSpecification, vault: CompanyVaultManager):
        """
        Independently discovers companies from API sources using the
        search specification, then enriches each discovered company with
        additional raw data from the same and other APIs.
        """
        discovered = {}  # company_name -> list[RawEvidence] from discovery step

        for name, evidence in self._discover_opencorporates(search_spec):
            discovered.setdefault(name, []).append(evidence)

        for name, evidence in self._discover_fmp_screener(search_spec):
            discovered.setdefault(name, []).append(evidence)

        for name, evidence in self._discover_fmp_search(search_spec):
            discovered.setdefault(name, []).append(evidence)

        for name, evidence in self._discover_alpha_vantage(search_spec):
            discovered.setdefault(name, []).append(evidence)

        for name, evidence in self._discover_clearbit(search_spec):
            discovered.setdefault(name, []).append(evidence)

        print(f"API discovery found {len(discovered)} companies.")

        for company_name, discovery_evidence in discovered.items():
            vault.add_company(company_name)

            for evidence in discovery_evidence:
                vault.add_evidence(company_name, evidence)

            # Pull extra enrichment now that we know the name exists.
            for evidence in self._enrich(company_name):
                vault.add_evidence(company_name, evidence)

    def _build_query_terms(self, search_spec: SearchSpecification):
        """
        Builds a generic free-text query plus a dict of structured
        constraint values (e.g. region, industry) pulled straight from
        the search specification.
        """
        text_query = search_spec.discovery_prompt or search_spec.objective
        return text_query, search_spec.constraints

    # ------------------------------------------------------------------
    # DISCOVERY: OpenCorporates company search
    # ------------------------------------------------------------------
    def _discover_opencorporates(self, search_spec: SearchSpecification):
        if not self.opencorporates_key:
            print("OpenCorporates: no API key set, skipping discovery.")
            return []

        text_query, constraints = self._build_query_terms(search_spec)
        jurisdiction = constraints.get("region") or constraints.get("country")

        params = {
            "q": text_query,
            "api_token": self.opencorporates_key,
        }
        if jurisdiction:
            params["jurisdiction_code"] = jurisdiction

        try:
            response = requests.get(
                "https://api.opencorporates.com/v0.4/companies/search",
                params=params,
                timeout=10,
            )
            if response.status_code != 200:
                return []

            data = response.json()
            companies = (
                data.get("results", {}).get("companies", [])
                if isinstance(data, dict)
                else []
            )

            output = []
            for entry in companies:
                company_data = entry.get("company", {})
                name = company_data.get("name")
                if not name:
                    continue

                evidence = RawEvidence(
                    source="OpenCorporates",
                    source_type="api",
                    url=company_data.get("opencorporates_url", "https://opencorporates.com"),
                    title="Company Registry Match",
                    metadata={"section": "discovery_registry"},
                    content=json.dumps(company_data),
                )
                output.append((name, evidence))

            return output
        except Exception as e:
            print(f"OpenCorporates discovery error: {e}")
            return []

    # ------------------------------------------------------------------
    # DISCOVERY: Financial Modeling Prep stock screener
    # ------------------------------------------------------------------
    def _discover_fmp_screener(self, search_spec: SearchSpecification):
        if not self.fmp_key:
            print("Financial Modeling Prep: no API key set, skipping screener.")
            return []

        _, constraints = self._build_query_terms(search_spec)

        params = {"apikey": self.fmp_key, "limit": 50}
        if "sector" in constraints:
            params["sector"] = constraints["sector"]
        if "industry" in constraints:
            params["industry"] = constraints["industry"]
        if "country" in constraints:
            params["country"] = constraints["country"]
        if "region" in constraints:
            params["country"] = constraints["region"]

        try:
            response = requests.get(
                "https://financialmodelingprep.com/api/v3/stock-screener",
                params=params,
                timeout=10,
            )
            if response.status_code != 200:
                return []

            data = response.json()
            if not isinstance(data, list):
                return []

            output = []
            for entry in data:
                name = entry.get("companyName")
                if not name:
                    continue

                evidence = RawEvidence(
                    source="FinancialModelingPrep",
                    source_type="api",
                    url="https://financialmodelingprep.com/api/v3/stock-screener",
                    title="Screener Match",
                    metadata={"section": "discovery_screener"},
                    content=json.dumps(entry),
                )
                output.append((name, evidence))

            return output
        except Exception as e:
            print(f"FMP screener discovery error: {e}")
            return []

    # ------------------------------------------------------------------
    # DISCOVERY: Financial Modeling Prep free-text company search
    # ------------------------------------------------------------------
    def _discover_fmp_search(self, search_spec: SearchSpecification):
        if not self.fmp_key:
            return []

        text_query, _ = self._build_query_terms(search_spec)

        try:
            response = requests.get(
                "https://financialmodelingprep.com/api/v3/search",
                params={"query": text_query, "limit": 50, "apikey": self.fmp_key},
                timeout=10,
            )
            if response.status_code != 200:
                return []

            data = response.json()
            if not isinstance(data, list):
                return []

            output = []
            for entry in data:
                name = entry.get("name")
                if not name:
                    continue

                evidence = RawEvidence(
                    source="FinancialModelingPrep",
                    source_type="api",
                    url="https://financialmodelingprep.com/api/v3/search",
                    title="Search Match",
                    metadata={"section": "discovery_search"},
                    content=json.dumps(entry),
                )
                output.append((name, evidence))

            return output
        except Exception as e:
            print(f"FMP search discovery error: {e}")
            return []

    # ------------------------------------------------------------------
    # DISCOVERY: Alpha Vantage symbol search
    # ------------------------------------------------------------------
    def _discover_alpha_vantage(self, search_spec: SearchSpecification):
        if not self.alpha_vantage_key:
            print("Alpha Vantage: no API key set, skipping discovery.")
            return []

        text_query, _ = self._build_query_terms(search_spec)

        try:
            response = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "SYMBOL_SEARCH",
                    "keywords": text_query,
                    "apikey": self.alpha_vantage_key,
                },
                timeout=10,
            )
            if response.status_code != 200:
                return []

            data = response.json()
            matches = data.get("bestMatches", [])

            output = []
            for entry in matches:
                name = entry.get("2. name")
                if not name:
                    continue

                evidence = RawEvidence(
                    source="AlphaVantage",
                    source_type="api",
                    url="https://www.alphavantage.co/query?function=SYMBOL_SEARCH",
                    title="Symbol Search Match",
                    metadata={"section": "discovery_symbol_search"},
                    content=json.dumps(entry),
                )
                output.append((name, evidence))

            return output
        except Exception as e:
            print(f"Alpha Vantage discovery error: {e}")
            return []

    # ------------------------------------------------------------------
    # DISCOVERY: Clearbit Discovery API
    # ------------------------------------------------------------------
    def _discover_clearbit(self, search_spec: SearchSpecification):
        if not self.clearbit_key:
            print("Clearbit: no API key set, skipping discovery.")
            return []

        text_query, constraints = self._build_query_terms(search_spec)

        query_string = text_query
        if "region" in constraints:
            query_string += f" {constraints['region']}"

        try:
            response = requests.get(
                "https://discovery.clearbit.com/v1/companies/search",
                params={"query": query_string, "limit": 50},
                headers={"Authorization": f"Bearer {self.clearbit_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                return []

            data = response.json()
            results = data.get("results", []) if isinstance(data, dict) else []

            output = []
            for entry in results:
                name = entry.get("name")
                if not name:
                    continue

                evidence = RawEvidence(
                    source="Clearbit",
                    source_type="api",
                    url="https://discovery.clearbit.com/v1/companies/search",
                    title="Discovery Match",
                    metadata={"section": "discovery_firmographic"},
                    content=json.dumps(entry),
                )
                output.append((name, evidence))

            return output
        except Exception as e:
            print(f"Clearbit discovery error: {e}")
            return []

    # ------------------------------------------------------------------
    # ENRICHMENT: once a company name is known, pull everything else
    # ------------------------------------------------------------------
    def _enrich(self, company_name: str):
        evidence_list = []
        evidence_list += self._enrich_financial_modeling_prep(company_name)
        evidence_list += self._enrich_clearbit_lookup(company_name)
        return evidence_list

    def _enrich_financial_modeling_prep(self, company_name: str):
        if not self.fmp_key:
            return []

        evidence_list = []

        try:
            search_resp = requests.get(
                "https://financialmodelingprep.com/api/v3/search",
                params={"query": company_name, "limit": 1, "apikey": self.fmp_key},
                timeout=10,
            )
            if search_resp.status_code != 200:
                return []

            matches = search_resp.json()
            if not matches:
                return []

            symbol = matches[0].get("symbol")
            if not symbol:
                return []

            endpoints = {
                "profile": f"https://financialmodelingprep.com/api/v3/profile/{symbol}",
                "income_statement": f"https://financialmodelingprep.com/api/v3/income-statement/{symbol}",
                "balance_sheet": f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{symbol}",
                "cash_flow": f"https://financialmodelingprep.com/api/v3/cash-flow-statement/{symbol}",
                "key_metrics": f"https://financialmodelingprep.com/api/v3/key-metrics/{symbol}",
            }

            for label, url in endpoints.items():
                try:
                    resp = requests.get(url, params={"apikey": self.fmp_key}, timeout=10)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    if not data:
                        continue

                    evidence_list.append(
                        RawEvidence(
                            source="FinancialModelingPrep",
                            source_type="api",
                            url=url,
                            title=label.replace("_", " ").title(),
                            metadata={"section": "financial", "report": label},
                            content=json.dumps(data),
                        )
                    )
                except Exception as e:
                    print(f"FMP {label} enrichment error for {company_name}: {e}")

        except Exception as e:
            print(f"FMP enrichment error for {company_name}: {e}")

        return evidence_list

    def _enrich_clearbit_lookup(self, company_name: str):
        if not self.clearbit_key:
            return []

        try:
            response = requests.get(
                "https://company.clearbit.com/v2/companies/find",
                params={"name": company_name},
                headers={"Authorization": f"Bearer {self.clearbit_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                return []

            data = response.json()

            return [
                RawEvidence(
                    source="Clearbit",
                    source_type="api",
                    url="https://company.clearbit.com/v2/companies/find",
                    title="Firmographic Profile",
                    metadata={"section": "business_inference"},
                    content=json.dumps(data),
                )
            ]
        except Exception as e:
            print(f"Clearbit enrichment error for {company_name}: {e}")
            return []


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
    worker = APIWorker()
    worker.discover(search_spec, vault)

    for company in vault.get_all_companies():
        print("\n" + "=" * 80)
        print(f"Company: {company.identity.name}")
        for evidence in company.raw_evidence:
            print(f"--- {evidence.source} / {evidence.title} ---")
            print(evidence.content[:500])
        print("=" * 80)