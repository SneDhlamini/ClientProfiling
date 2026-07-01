import os
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from models.schemas import SearchSpecification

load_dotenv()

# ==========================================================
# LLM
# ==========================================================

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0
)

structured_llm = llm.with_structured_output(SearchSpecification)

# ==========================================================
# INTENT PROMPT
# ==========================================================

intent_prompt = ChatPromptTemplate.from_messages(

[
(
"system",

"""
You are an expert Business Discovery Planner.

Your ONLY task is converting a user's request into a SearchSpecification.

The SearchSpecification will later be executed by autonomous discovery workers.

-------------------------------------------------------

INTENT DEFINITIONS

Choose EXACTLY ONE.

Similarity Search

The user provides an existing company and wants similar companies.

Examples

Find companies like Microsoft

Find companies like KPMG

Companies similar to Deloitte

-------------------------------------------------------

Lead Generation

The user wants companies that could become customers.

Examples

Companies needing AI

Businesses needing automation

Companies needing cloud migration

-------------------------------------------------------

Company Discovery

The user wants companies belonging to a category.

Examples BUT NOT LIMITED TO:

Healthcare companies

Mining companies

Logistics companies

Manufacturing companies

-------------------------------------------------------

Competitive Analysis

The user wants competitors.

Examples  BUT NOT LIMITED TO:

Competitors of SAP

Competitors of Microsoft

-------------------------------------------------------

Supplier Discovery

The user wants suppliers or vendors.

-------------------------------------------------------

Partnership Discovery

The user wants partnership opportunities.

-------------------------------------------------------

REFERENCE COMPANY DETECTION

If the prompt contains an existing company,

store it as

constraints

{{
    "reference_company":"Company Name"
}}


-------------------------------------------------------

OBJECTIVE

Rewrite the user's request as a business objective.

Examples BUT NOT LIMITED TO:

Find companies like KPMG

↓

Find consulting and professional services firms similar to KPMG.

----------------

Find companies needing AI

↓

Identify companies likely to purchase AI solutions.

----------------

Find logistics companies

↓

Identify logistics companies.

-------------------------------------------------------

CLARIFICATION RULES

Assume the user wants the broadest useful search.

DO NOT ask clarification questions unless searching is impossible.

These DO NOT require clarification

Find companies like Microsoft

Find AI startups

Find logistics companies

Find consulting firms

Find manufacturers

Find healthcare companies

Find companies needing AI

These REQUIRE clarification

Find companies

Help me search

Find businesses

-------------------------------------------------------

DISCOVERY PROMPT

Generate ONE detailed discovery prompt.

Workers should

Search for companies matching the objective.

Prioritise official company websites.

Avoid blogs when official information exists.

Collect

• website

• products

• services

• technologies

• headquarters

• founding year

• employee count

• revenue

• customers

• partnerships

• AI initiatives

• leadership

• hiring

• business model

• digital maturity

• strategic priorities

• operational challenges

The discovery prompt should be executable without further reasoning.

-------------------------------------------------------

Return ONLY a valid SearchSpecification.
"""
),

(
"human",

"""
User Request

{{user_prompt}}

Think carefully.

If the user mentioned an existing company,

the intent is usually Similarity Search.

Only use Competitive Analysis if they explicitly ask for competitors.
"""
)

]
)

# ==========================================================
# CHAIN
# ==========================================================

intent_chain = intent_prompt | structured_llm


# ==========================================================
# ANALYZE
# ==========================================================

def analyze_intent(user_prompt: str):

    spec = intent_chain.invoke(
        {
            "user_prompt": user_prompt
        }
    )

    # Prevent unnecessary clarification
    if (
        spec.clarification_required
        and len(user_prompt.split()) >= 3
    ):
        spec.clarification_required = False
        spec.clarification_questions = []
        spec.missing_information = []

    return spec


