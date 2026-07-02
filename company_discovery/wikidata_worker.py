import requests

from models.schemas import RawEvidence
from company_vault.vault import CompanyVaultManager

WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"


class WikidataWorker:
    """
    Supplementary enrichment worker (not a discovery worker). Looks up each
    company already in the vault on Wikidata and, if a confident business
    match exists, stores its structured facts as evidence.

    Free, no API key required. Coverage is strong for large/well-known
    companies and weak-to-nonexistent for small private companies - this
    is a bonus enrichment pass, not something to rely on for most leads.
    """

    def __init__(self):
        self.session = requests.Session()
        # Wikidata asks for a descriptive User-Agent on all requests.
        self.session.headers.update({
            "User-Agent": "ClientProfilingBot/1.0 (company research project)"
        })

    def enrich(self, vault: CompanyVaultManager):
        for company in vault.get_all_companies():
            entity_id = self._find_entity(company.identity.name)
            if not entity_id:
                continue

            facts_text = self._fetch_entity_facts(entity_id, company.identity.name)
            if not facts_text:
                continue

            vault.add_evidence(
                company.identity.name,
                RawEvidence(
                    source="WikidataWorker",
                    source_type="wikidata",
                    url=f"https://www.wikidata.org/wiki/{entity_id}",
                    title="Wikidata Entity",
                    metadata={"section": "wikidata_facts", "entity_id": entity_id},
                    content=facts_text,
                    confidence=0.85,
                ),
            )
            print(f"  -> Wikidata match for {company.identity.name}: {entity_id}")

    # ------------------------------------------------------------------
    # Entity lookup + type confirmation
    # ------------------------------------------------------------------
    def _find_entity(self, company_name: str) -> str | None:
        """
        Searches Wikidata for the name, then confirms the top candidate is
        actually a business (instance/subclass of 'business', Q4830453)
        to avoid matching unrelated entities (people, films, etc.) that
        happen to share the name.
        """
        try:
            resp = self.session.get(
                WIKIDATA_SEARCH_URL,
                params={
                    "action": "wbsearchentities",
                    "search": company_name,
                    "language": "en",
                    "type": "item",
                    "limit": 5,
                    "format": "json",
                },
                timeout=10,
            )
            resp.raise_for_status()
            candidates = resp.json().get("search", [])
        except Exception as e:
            print(f"Wikidata search error for {company_name}: {e}")
            return None

        for candidate in candidates:
            entity_id = candidate.get("id")
            if entity_id and self._is_business_entity(entity_id):
                return entity_id

        return None

    def _is_business_entity(self, entity_id: str) -> bool:
        query = f"""
        ASK {{
          wd:{entity_id} wdt:P31/wdt:P279* wd:Q4830453 .
        }}
        """
        try:
            resp = self.session.get(
                WIKIDATA_SPARQL_URL,
                params={"query": query, "format": "json"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("boolean", False)
        except Exception as e:
            print(f"Wikidata type-check error for {entity_id}: {e}")
            return False

    # ------------------------------------------------------------------
    # Fact retrieval
    # ------------------------------------------------------------------
    def _fetch_entity_facts(self, entity_id: str, company_name: str) -> str | None:
        query = f"""
        SELECT ?industryLabel ?inception ?hqLabel ?website ?employees WHERE {{
          OPTIONAL {{ wd:{entity_id} wdt:P452 ?industry. }}
          OPTIONAL {{ wd:{entity_id} wdt:P571 ?inception. }}
          OPTIONAL {{ wd:{entity_id} wdt:P159 ?hq. }}
          OPTIONAL {{ wd:{entity_id} wdt:P856 ?website. }}
          OPTIONAL {{ wd:{entity_id} wdt:P1128 ?employees. }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT 1
        """
        try:
            resp = self.session.get(
                WIKIDATA_SPARQL_URL,
                params={"query": query, "format": "json"},
                timeout=10,
            )
            resp.raise_for_status()
            bindings = resp.json().get("results", {}).get("bindings", [])
        except Exception as e:
            print(f"Wikidata facts query error for {company_name}: {e}")
            return None

        if not bindings:
            return None

        row = bindings[0]
        lines = [f"Wikidata entity for {company_name} ({entity_id}):"]
        if "industryLabel" in row:
            lines.append(f"Industry: {row['industryLabel']['value']}")
        if "inception" in row:
            lines.append(f"Founded: {row['inception']['value'][:10]}")
        if "hqLabel" in row:
            lines.append(f"Headquarters: {row['hqLabel']['value']}")
        if "website" in row:
            lines.append(f"Website: {row['website']['value']}")
        if "employees" in row:
            lines.append(f"Employees: {row['employees']['value']}")

        # Only the header line means nothing useful came back.
        if len(lines) == 1:
            return None

        return "\n".join(lines)


# testing
if __name__ == "__main__":
    vault = CompanyVaultManager()
    vault.add_company("Microsoft")
    vault.add_company("Bain & Company")

    worker = WikidataWorker()
    worker.enrich(vault)

    for company in vault.get_all_companies():
        print("\n" + "=" * 80)
        print(f"Company: {company.identity.name}")
        for evidence in company.raw_evidence:
            print(f"--- {evidence.title} ---")
            print(evidence.content)