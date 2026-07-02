from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class SearchSpecification(BaseModel): #pydantic models inherit from BaseModel
    intent: str = Field(
        description= (
        "The primary search intent such as Similarity Search, Lead Generation, "
          "Market Research, Company Discovery, or Competitive Analysis."
    )
    )

    objective: str = Field(
        description=(
          "The user's business objective."
        
        )
    )

    constraints: Dict[str, str] = Field(
        default_factory=dict, #so that if there are no constraints we have a default empty dict
        description= "All extracted search constraints"
    )
    required_attributes: List[str]= Field(
        default_factory=list, # if there are no required attributes returns empty list
        description="Business attributes needed for evaluation"
    )

    clarification_required: bool = Field(
        description="True only if the search cannot proceed reliably without additional user information."
    )

    missing_information: List[str] = Field(
        default_factory=list,
        description="Essential information that prevents the search from proceeding."
    )

    clarification_questions: List[str] = Field(
        default_factory=list,
        description=(
        "Set to True ONLY if the search cannot continue reliably. "
        "Do NOT request clarification if the search can reasonably proceed "
        "using the information already provided."
    )
    )

    confidence: float = Field(
        default=0.0,
        description=(
        "A confidence score between 0.0 and 1.0 indicating how certain the "
        "agent is that it correctly understood the user's request."
    )
    )

    discovery_prompt: str = Field(
    default="",
    description=(
        "A detailed search strategy generated during intent analysis. " 
        "This prompt tells every discovery worker exactly what kinds of " 
        "companies to find, what to prioritize, and what to ignore."
    )

    )






 #this will just store company ID basically
class CompanyIdentity(BaseModel):
    """
    Information that uniquely identifies a company
    """
    name: str = Field(
     description = "Official company name."
    )

    website: Optional[str] = Field(
        default=None,
        description="Official company website URL."
    )







class RawEvidence(BaseModel):
    """
    Raw information collected by discovery workers.
    """
    source: str = Field(
        description="which worker discovered this evidence."
    )

    source_type: str = Field(
        description="The type of source, e.g., web, database, API."
    )

    url: Optional[str] = Field(
        default=None,
        description="URL of the source if applicable."
    )

    title: str = Field(
        description="A brief title or headline for the evidence."
    )

    metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Additional metadata about the evidence."
    )

    content: str = Field(
        description="The content of the evidence."
    )
    confidence: float = Field(
        default=1.0,
        description="A confidence score between 0.0 and 1.0 indicating how certain the agent is about the evidence."
    )









#Company factual info
class CompanyFacts(BaseModel):
    """
    Objective factual information about a company, derived from raw evidence.
    """
    industry: Optional[str] = None
    revenue: Optional[str] = None
    employee_count: Optional[str] = None
    founding_year: Optional[str] = None
    headquarters: Optional[str] = None
    countries:List[str] = Field(default_factory=list)
    products: List[str] = Field(default_factory=list)
    services: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    business_model: Optional[str] = None
    current_clients: List[str] = Field(default_factory=list)
    sales_contact_details: Optional[str] = None







class SemanticProfile(BaseModel):
    """
    A semantic representation of a company's business model, market positioning, and strategic focus.
    """
    ai_readiness: Optional[str] = None
    innovation_focus: Optional[str] = None
    innovation_level: Optional[str] = None
    growth_stage: Optional[str] = None
    business_health: Optional[str] = None
    enterprise_readiness: Optional[str] = None
    partnership_potential: Optional[str] = None
    procurement_complexity: Optional[str] = None
    investment_capacity: Optional[str] = None
    operational_challenges: List[str] = Field(default_factory=list)
    technology_gaps: List[str] = Field(default_factory=list)
    ai_opportunities: List[str] = Field(default_factory=list)
    automation_opportunities: List[str] = Field(default_factory=list)
    likely_business_goals: List[str] = Field(default_factory=list)
    strategic_priorities: List[str] = Field(default_factory=list)
    risk_factors: List[str] = Field(default_factory=list)
    



# this one will store for each company before they all infor goes to the vault
class CompanyProfile(BaseModel):
    """
    Complete knowledge repository for one company
    """
    identity: CompanyIdentity

    raw_evidence: List[RawEvidence]= Field(
        default_factory=list,
    )

    facts: CompanyFacts = Field(
        default_factory=CompanyFacts,
    )

    semantic_profile: SemanticProfile = Field(
        default_factory=SemanticProfile,
    )   

    metadata: Dict[str, str] = Field(
        default_factory=dict,  
    )


class CompanyVault(BaseModel):
    companies: Dict[str, CompanyProfile] = Field(
        default_factory=dict,
    )
    





#returns both objective fact and semantic reasoning
class CompanyAnalysis(BaseModel):
    #complete AI-generated understading of a company

    facts: CompanyFacts
    semantic_profile: SemanticProfile