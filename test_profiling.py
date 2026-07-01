from company_vault.vault import CompanyVaultManager
from company_profiling.profiler import CompanyProfiler
from models.schemas import RawEvidence
# DONT FORGET TO DELETEEE THISSSSSS
# Create vault
vault = CompanyVaultManager()

# Add a test company
vault.add_company(
    "Microsoft",
    "https://www.microsoft.com"
)

vault.add_evidence(
    "Microsoft",
    RawEvidence(
        source="Web Worker",
        source_type="Website",
        title="Homepage",
        content="""
Microsoft develops cloud computing,
AI, Microsoft Azure,
Microsoft 365 and enterprise software.
The company employs approximately
230000 people worldwide.
"""
    )
)

# Run profiler
profiler = CompanyProfiler()

profiler.profile(vault)

# View results
company = vault.get_company("Microsoft")

print(company.facts)
print()
print(company.semantic_profile)