from prompt.prompt import analyze_intent

from company_vault.vault import CompanyVaultManager

from company_discovery.web_worker import WebWorker
from company_discovery.linkedin_worker import LinkedInWorker

from company_profiling.profiler import CompanyProfiler


# ------------------------------------------
# EDIT THIS LINE to change what you're searching for, then run the script.
# ------------------------------------------
SEARCH_QUERY = "find AI consulting companies in South Africa"


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

    # Later

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