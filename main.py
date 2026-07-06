from prompt.prompt import analyze_intent

from company_vault.vault import CompanyVaultManager

from company_discovery.web_worker import WebWorker
from company_discovery.linkedin_worker import LinkedInWorker
from company_discovery.wikidata_worker import WikidataWorker

from company_profiling.profiler import CompanyProfiler

from client_scoring.scorer import ClientScorer
from client_scoring.dashboard import DashboardGenerator

# ------------------------------------------
# EDIT THIS LINE to change what you're searching for, then run the script.
# ------------------------------------------
SEARCH_QUERY = "high ranking companies in Auditing in Africa"

def main():

    # ------------------------------------------
    # USER PROMPT
    # ------------------------------------------

    user_prompt = SEARCH_QUERY
    print(f"[DEBUG] You searched for: {user_prompt!r}")

    # ------------------------------------------
    # INTENT ANALYSIS
    # ------------------------------------------

    print("\nAnalyzing prompt...")

    search_spec = analyze_intent(
        user_prompt
    )

    print(search_spec)

    if search_spec.clarification_required:
        print("\nI need a bit more information before I can search:")
        for question in search_spec.clarification_questions:
            print(f"  - {question}")
        if search_spec.missing_information:
            print(f"\n(Missing: {', '.join(search_spec.missing_information)})")
        return

    # ------------------------------------------
    # CREATE COMPANY VAULT
    # ------------------------------------------

    vault = CompanyVaultManager()

    # ------------------------------------------
    # DISCOVERY
    # ------------------------------------------

    print("\nRunning Web Worker...")

    web_worker = WebWorker()

    web_worker.discover(
        search_spec,
        vault
    )

    print("\nRunning LinkedIn Worker...")

    linkedin_worker = LinkedInWorker()

    linkedin_worker.discover(
        search_spec,
        vault
    )

    print("\nRunning Wikidata Worker (enrichment)...")

    wikidata_worker = WikidataWorker()

    wikidata_worker.enrich(
        vault
    )

    # Later

    # registry_worker.discover(...)
    # news_worker.discover(...)
    # pdf_worker.discover(...)

    print()

    vault.summary()

    # ------------------------------------------
    # COMPANY PROFILING (AI - structured facts)
    # ------------------------------------------

    print("\nProfiling companies...\n")

    profiler = CompanyProfiler()

    for company in vault.get_all_companies():
        try:
            profiler.profile(company, vault)
        except Exception as e:
            print(f"Profiling error for {company.identity.name}: {e}")

    # ------------------------------------------
    # CLIENT SCORING (deterministic, no AI)
    # ------------------------------------------

    print("\nScoring companies against the search prompt...\n")

    scorer = ClientScorer()
    ranked_companies = scorer.score_all(vault, search_spec)

    for company, score, breakdown in ranked_companies:
        print(f"  {round(score * 100):>3}%  {company.identity.name}")

    # ------------------------------------------
    # OUTPUT
    # ------------------------------------------

    dashboard_generator = DashboardGenerator()
    dashboard_path = dashboard_generator.generate(ranked_companies, search_spec)

    print(f"\nDashboard written to: {dashboard_path}")
    print("Open it in your browser to view the interactive results.")


if __name__ == "__main__":
    main()