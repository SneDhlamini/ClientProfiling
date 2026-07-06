"""
    user prompt (text)
        -> prompt.analyze_intent()      turns it into a SearchSpecification
        -> WebWorker / LinkedInWorker / APIWorker   discover companies +raw evidence, in parallel, all writing into one shared vault
        
"""

import concurrent.futures

from models.schemas import SearchSpecification
from company_vault.vault import CompanyVaultManager

from prompt.prompt import analyze_intent
from web_worker import WebWorker
from linkedin_worker import LinkedInWorker
from wikidata_worker import WikidataWorker
from company_profiling.profiler import CompanyProfiler


# Every worker exposes the same interface: worker.discover(search_spec, vault)
DISCOVERY_WORKERS = [WebWorker, LinkedInWorker,WikidataWorker]


def build_search_spec(user_prompt: str) -> SearchSpecification:
    
    #Converts user prompt to a good web search 

    return analyze_intent(user_prompt)


def run_discovery_workers(search_spec: SearchSpecification, vault: CompanyVaultManager):
    """
    Runs every worker against the same SearchSpecification and the same vault
    Workers are independent of each other so they run concurrently and each worker's
    failure is isolated 
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(DISCOVERY_WORKERS)) as pool:
        futures = {
            pool.submit(worker_cls().discover, search_spec, vault): worker_cls.__name__
            for worker_cls in DISCOVERY_WORKERS
        }
        for future in concurrent.futures.as_completed(futures):
            worker_name = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"{worker_name} failed: {e}")


def profile_companies(vault: CompanyVaultManager):
    """
    Runs the profiler over every company that has at least one piece of
    raw evidence. Companies with no evidence are skipped rather than sent to the
    LLM with nothing to reason over.
    """
    profiler = CompanyProfiler()
    for company in vault.get_all_companies():
        if not company.raw_evidence:
            continue
        try:
            profiler.profile(company, vault)
        except Exception as e:
            print(f"Profiling failed for {company.identity.name}: {e}")


def discover_companies(user_prompt: str, vault: CompanyVaultManager | None = None) -> CompanyVaultManager:
    """
    Full pipeline. 
      - identity (name, website)
      - raw_evidence (everything workers collected, source-attributed)
      - facts (structured, extracted-only-from-evidence business facts)
      - semantic_profile (LLM inferences: AI readiness, growth stage, etc.)
    """
    search_spec = build_search_spec(user_prompt)
    print(f"Intent: {search_spec.intent}")
    print(f"Objective: {search_spec.objective}")
    if search_spec.constraints:
        print(f"Constraints: {search_spec.constraints}")

    if vault is None:
        vault = CompanyVaultManager()

    run_discovery_workers(search_spec, vault)
    print(f"Discovery complete: {vault.company_count()} companies, {vault.evidence_count()} evidence records.")

    profile_companies(vault)

    return vault

#testinggggg
if __name__ == "__main__":
    vault = discover_companies("Find companies in South Africa that need AI solutions")
    vault.summary()