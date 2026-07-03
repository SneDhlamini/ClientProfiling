from company_vault import vault
from prompt.prompt import analyze_intent

from company_vault.vault import CompanyVaultManager

from company_discovery.web_worker import WebWorker
from company_discovery.linkedin_worker import LinkedInWorker
from company_discovery.wikidata_worker import WikidataWorker

from company_profiling.profiler import CompanyProfiler


from client_scoring.scorer import ClientScorer
from client_scoring.dashboard import DashboardGenerator

# ------------------------------------------
# Put search prompt here.
# ------------------------------------------
SEARCH_QUERY = "I want consulting companies that have been in business for at least 10 years founded by Africans. they should be profitable and have sales of over 40millon dollars"


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

    # to add laterr

    # registry_worker.discover(...)
    # news_worker.discover(...)
    # pdf_worker.discover(...)

    print()

    vault.summary()

        # ------------------------------------------
    # COMPANY PROFILING
    # ------------------------------------------

    print("\nProfiling companies...\n")

    profiler = CompanyProfiler()

    for company in vault.get_all_companies():
        profiler.profile(
            company,
            vault
        )

    # ------------------------------------------
    # CLIENT SCORING
    # ------------------------------------------

    print("\nScoring companies...\n")

    scorer = ClientScorer()

    scored_companies = scorer.score_all(
        vault,
        search_spec
    )

    # ------------------------------------------
    # DASHBOARD
    # ------------------------------------------

    print("\nGenerating dashboard...\n")

    dashboard = DashboardGenerator()

    dashboard_path = dashboard.generate(
        scored_companies,
        search_spec
    )

    print(f"Dashboard generated: {dashboard_path}")    # ------------------------------------------
    # COMPANY PROFILING
    # ------------------------------------------

    print("\nProfiling companies...\n")

    profiler = CompanyProfiler()

    for company in vault.get_all_companies():
        profiler.profile(
            company,
            vault
        )

    # ------------------------------------------
    # CLIENT SCORING
    # ------------------------------------------

    print("\nScoring companies...\n")

    scorer = ClientScorer()

    scored_companies = scorer.score_all(
        vault,
        search_spec
    )

    # ------------------------------------------
    # DASHBOARD
    # ------------------------------------------

    print("\nGenerating dashboard...\n")

    dashboard = DashboardGenerator()

    dashboard_path = dashboard.generate(
        scored_companies,
        search_spec
    )

    print(f"Dashboard generated: {dashboard_path}")    # ------------------------------------------
    # COMPANY PROFILING
    # ------------------------------------------

    print("\nProfiling companies...\n")

    profiler = CompanyProfiler()

    for company in vault.get_all_companies():
        profiler.profile(
            company,
            vault
        )

    # ------------------------------------------
    # CLIENT SCORING
    # ------------------------------------------

    print("\nScoring companies...\n")

    scorer = ClientScorer()

    scored_companies = scorer.score_all(
        vault,
        search_spec
    )

    # ------------------------------------------
    # DASHBOARD
    # ------------------------------------------

    print("\nGenerating dashboard...\n")

    dashboard = DashboardGenerator()

    dashboard_path = dashboard.generate(
        scored_companies,
        search_spec
    )

    print(f"Dashboard generated: {dashboard_path}")
    # ------------------------------------------
    # OUTPUT
    # ------------------------------------------

    print("\n\n================ COMPANY PROFILES ================\n")

    for company in vault.get_all_companies():

        print("=" * 80)

        print(f"Company: {company.identity.name}")

        print(f"Website: {company.identity.website}")

        print("\nFACTS")

        print(company.facts)

        print("\nSEMANTIC PROFILE")

        print(company.semantic_profile)

        print("=" * 80)


if __name__ == "__main__":
    main()


