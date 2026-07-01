import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

from langchain_core.prompts import ChatPromptTemplate
from models.schemas import SearchSpecification


load_dotenv()
#Initialize Groq 
llm = ChatGroq(
    model="llama-3.3-70b-versatile", 
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0 #temprature controls the randomness of the output. Lower values make the output more deterministic, while higher values make it more random.
)


structured_llm = llm.with_structured_output(SearchSpecification) # force model to return data that matches the Pydantic Model

#prompt template
intent_prompt=ChatPromptTemplate.from_messages([  #just a template
    ("system", 
    """
    You are an expert intent analysis agent. Your task is to analyze the user's input and determine the underlying intent for an AI-powered company discovery platform.
    
    Your responsibility is to understand a user's business search request and convert it into a structured Search Specification
    
    Your objectives are:
    1. identify the user's primary search intent
    2. Determine the user's business objective 
    3. Extract all relevant parameters from the user's input that can be used to refine the search results
    4. Never invent or assume missing information
    5. If clarification is required, indicate exactly what information is needed
    6. If sufficient information exists, produce a complete Search Specification.
    7. Be objective, concise and consistent. 
    8. Generate a detailed discovery_prompt that instructs downstream discovery workers how to search for companies.
     
    

    The discovery_prompt should be a complete instruction for downstream discovery workers.

     It must include:

    1. The type of companies to discover.
    2. Similarity or selection criteria.
    3. Industries to prioritise.
    4. Geographic constraints.
    5. Trusted sources.
    6. Information to collect including:

   - website
   - services
   - products
   - industry
   - employee count
   - revenue
   - technologies
   - AI initiatives
   - partnerships
   - customers
   - leadership
   - hiring activity
   - digital maturity

   The discovery_prompt should be executable by a discovery worker without requiring additional reasoning.


    Clarification Rules

   Assume the user wants the broadest reasonable search.
   Do NOT ask clarification questions simply because the search could be more specific.
   Proceed whenever a useful company search can begin.
   Only request clarification when the search would otherwise be impossible.
   Examples that SHOULD NOT require clarification:

    - Find companies like Microsoft
    - Find AI startups
    - Find companies needing AI
    - Find logistics companies
    - Find competitors to KPMG
    - Find healthcare companies

    Examples that SHOULD require clarification:

    - Find companies
    - Help me search
    - I need businesses

    Examples

     User:
     Find companies like KPMG

     intent:
     Similarity Search

    objective:
    Find companies similar to KPMG

constraints:
{{
    "reference_company":"KPMG"
}}

clarification_required:
False

------------------------------------------------

User:
Find companies that need AI solutions

intent:
Lead Generation

objective:
Find companies likely to benefit from AI solutions

constraints:
{{}}

clarification_required:
False

------------------------------------------------

User:
Find manufacturing companies in South Africa

intent:
Company Discovery

objective:
Find manufacturing companies

constraints:
{{
    "industry":"Manufacturing",
    "region":"South Africa"
}}

clarification_required:
    False

------------------------------------------------

IMPORTANT: The examples above are ONLY illustrations of the expected
output FORMAT. They are not related to the current request in any way.
Do NOT reuse "KPMG", "manufacturing", "South Africa", or any other
example detail unless the user's actual request below explicitly
mentions it. Base every field strictly and only on the User Request
given in the human message that follows.
    """
    ),
    (
     "human",
     """
Analyze ONLY the following request. Ignore all example content shown
in the system instructions above.

User Request:
{user_prompt}
"""
    )
])

#Chain
intent_chain =intent_prompt | structured_llm  #this is a chain that takes the output of the intent_prompt and feeds it into the structured_llm


def analyze_intent(user_prompt: str):
    response = intent_chain.invoke(  #the .invoke changes it from a template to a conversation
        {
            "user_prompt": user_prompt
        }
    )
    #response = llm.invoke(prompt)
    return response


#test code
if __name__ == "__main__":
    response = analyze_intent(
        "Find companies that need AI solutions."
    )

    print(response)