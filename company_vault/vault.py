from models.schemas import CompanyProfile, CompanyIdentity, RawEvidence,CompanyVault

class CompanyVaultManager:
    """ 
    Central Storage containing every discovered company
    Every workers writes here
    Profiling and Scoring will read from here
    """
    def __init__(self):
        self.companies = {}
    
    def add_company(self, company_name: str, website: str |None=None):
        if company_name not in self.companies:
            self.companies[company_name] = CompanyProfile(
                identity=CompanyIdentity(
                    name=company_name,
                    website= website,
                    )
            )
        elif website:

            company= self.companies[company_name]
            if not company.identity.website:
                company.identity.website=website


    def company_exists(self,company_name: str):
        return company_name in self.companies            
    

    def get_company(self, company_name: str):
        return self.companies.get(company_name)
    

    def get_all_companies(self):
        return list(self.companies.values()
                    )
    


    #evidence
    def add_evidence(
        self,
        company_name: str,
        evidence: RawEvidence
    ):
        
    #to avoid deduplication. so if the company name already exirs it will not add a new one but rather just add evidence to the exisitng name
        if not self.company_exists(company_name):
            self.add_company(company_name)

        self.companies[company_name].raw_evidence.append(evidence)




    def update_facts(
            self,
            company_name: str,
            **kwargs
    ):
        company = self.get_company(company_name)


        if not company:
            return
        
        for key, value in kwargs.items():
            if hasattr(company.facts, key):
                setattr(
                    company.facts,
                    key,
                    value,
                )


# a SemanticProfile 

    def update_semantic_profile(
        self,
        company_name: str,
        **kwargs
        ):

        company =self.get_company(company_name)
        if not company:
            return
        
        for key, value in kwargs.items():
            if hasattr(company.semantic_profile,key):
                setattr(
                    company.semantic_profile,
                    key,
                    value,
                )











# statistics count
    def company_count(self):
        return len(self.companies)


    def evidence_count(self):
        return sum(len(company.raw_evidence)
                   for company in self.companies.values()
                   )  





    def summary(self):
        print("\n -------------COMPANY VAULT---------------")
        print(f"Companies: {self.company_count()}")
        print(f"Evidence:{self.evidence_count()}")

        for company in self.get_all_companies():
            print("-"* 50) 
            print(company.identity.name)
            print(f"Website: {company.identity.website}")
            print(f"Evidence: {len(company.raw_evidence)}")