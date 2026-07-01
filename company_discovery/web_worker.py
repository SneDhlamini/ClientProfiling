from prompt.prompt import llm
from models.schemas import SearchSpecification, RawEvidence, CompanyProfile,CompanyIdentity
from company_vault.vault import CompanyVaultManager
#for web reading 
import requests
import trafilatura
from bs4 import BeautifulSoup

import os
from dotenv import load_dotenv
from tavily import TavilyClient
#it will search the web and find articles that have company names that match the prompt
#then it will read from those articles to extract the comapny name and then go visit said comapny websites 
load_dotenv()
class WebWorker:
    def __init__(self):
        self.llm = llm
        self.tavily=TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    

    def discover(
      self,  
      search_spec: SearchSpecification,
      vault: CompanyVaultManager
       ):
       query = self._build_search_query(search_spec)
       results = self._search_web(query)
       companies= self.extract_candidate_companies(results,search_spec)
       print(companies)



    def _build_search_query(
           self,
           search_spec: SearchSpecification
            ) -> str:
            query_parts = []

            query_parts.append(search_spec.objective)

            for key, value in search_spec.constraints.items():
             query_parts.append(value)

            return " ".join(query_parts)
    



    #given a seahrch query it searchs the web
    def _search_web(self,query: str):
       
       response = self.tavily.search(
           query=query,
           search_depth="advanced",
           max_results=5     # increase this laterr

       )
       return response.get("results",[])







  # to take company name from website and not the website artivle itself 
    def extract_candidate_companies(self,results,search_spec: SearchSpecification):
        """
        Uses the LLM to extract actual company names from 
        Tavily search results
        """


        search_text= ""
        for result in results:
         title=result.get( "title","")
         content= result.get("content","")

        search_text +=f"""
    Title:
    {title}

    Content:
    {content}
    ------------------------------------------------------
    """
        prompt=f"""
    You are a business intelligence Analyst
    Below are search results collected from the web.
    Your task is not to summarize them
    Instead, identify every REAL COMPANY mentioned.

    Rules:
    -Return only company names 
    -Ignore Articles 
    -Ignore websites that are NOT companies.
    -Remove duplicates
    -If no companies exist, return an empty list

    Search Results:
    {search_text}
    """
        
        response=self.llm.invoke(prompt)

        companies= [
            company.replace("•", "" ).replace("-","").strip()
            for company in response.content.split("\n")
            if company.strip()
        ]
        return companies







    def read_page(
            self,
            url:str
    )-> str | None:
        """
        Download a webpage and extract the readable text"""
        try :
            response = requests.get(
                url,
                timeout=10,
                headers={
                    "User-Agent":  #so we can be accepted by wesites 
                    "Mozilla/5.0"
                }
            )

            if response.status_code != 200:
                return None

            extracted=(
                trafilatura.extract(
                    response.text
                )
            )
            return extracted
        except Exception as e:
            print(f"Could not read {url}: {e}")
            return None




    
  


















#testnnngggg 
if __name__ == "__main__":


    # Create a sample SearchSpecification
    search_spec = SearchSpecification(
        intent="Company Discovery",
        objective="Find companies that need AI solutions",
        constraints={
            "region": "South Africa"
        },
        required_attributes=[],
        clarification_required=False,
        missing_information=[],
        clarification_questions=[],
        confidence=0.95
    )

    # Create an empty vault
    vault = CompanyVaultManager()

    # Create the worker
    worker = WebWorker()

    # Run it
    worker.discover(search_spec, vault)
    for company in vault.get_all_companies(): # formating the output 
       print("\n"+"="* 80)
       print(
        f"Company: {company.identity.name}"
       )

       print(
          f"Website: {company.identity.website}"
      )

       print("\nContent:")

       for evidence in company.raw_evidence:

        print(
            evidence.content
        )

       print("=" * 80)

            