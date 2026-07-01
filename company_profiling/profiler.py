from langchain_core.prompts import ChatPromptTemplate

from prompt.prompt import llm 
from company_vault.vault import CompanyVaultManager
from models.schemas import CompanyAnalysis

class CompanyProfiler:
    def __init__(self):
        self.analysis_llm = llm.with_structured_output(
            CompanyAnalysis
        )

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
            "system",
            """
            You are an expert business intelligence analyst

            You are given evidence collected  from many independent sources about one company.
            Your job is to build the most complete and objective profile possible. 
            You must perform TWO tasks
            --------------------------------------------------------------------------------------
            task 1: Extact objective business facts
            examples include 
            -industry 
            -headquarters
            -employee count
            -products
            -services
            -technologies
            -business model
            -current clients
            -countries 
            -founding year
            -revenue
            -sales contact details 

            Only extract facts supported by evidence 
            Never invent information or make assumptions.
            --------------------------------------------------------------------------------------
            Task 2: Reason about the company
            Infer business characteristics 

            examples include 
            -AI readiness
            -Innovation level
            -Growth stage
            -Business health
            -digital health
            -Enterprise readiness
            -investment capacity
            -partnership potential
            -likely product purchases
            -likely operation challenges 
            -likely customer pain point
            -likely AI opportunities
            -likely automation opportunities

            Only make inferences that are strongly supported by available evidence

            if evidence is weak leave the fields empty

            Return ONLY  structured data
            """ ),
               ( 
                  "human",
                  """
                Company 
                
                {name}
                
                Evidence
                
                {evidence}"""
                ),
            ]
        )
    

    def profile(
            self,
            company,
            vault 
    ):
        evidence=self.build_evidence_document(
            company
        )

        prompt= self.prompt.invoke(
            {
                "name": company.identity.name,
                "evidence": evidence,
            }
        )
        
        analysis = self.analysis_llm.invoke(
            prompt
        )
        vault.update_facts(
            company.identity.name,
            **analysis.facts.model_dump(
                exclude_none= True
            )
        )
        vault.update_semantic_profile(
            company.identity.name,
            **analysis.semantic_profile.model_dump(
                exclude_none= True
            )
        )
       
    
    
    def build_evidence_document(
            self,
            company
    ):
       sections= []

       for evidence in company.raw_evidence:
              sections.append(
                 f"""
                 SOURCE: {evidence.source}
                 TYPE: {evidence.source_type}
                 CONTENT: {evidence.content}
                 """
                )
              

              return "\n".join(sections)    