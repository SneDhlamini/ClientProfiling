from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal


# ==========================================================
# SEARCH SPECIFICATION
# ==========================================================

class SearchSpecification(BaseModel):

    intent: Literal[
        "Similarity Search",
        "Lead Generation",
        "Market Research",
        "Company Discovery",
        "Supplier Discovery",
        "Partnership Discovery",
        "Competitive Analysis"
    ]

    objective: str = Field(
        description="Business objective of the search."
    )

    constraints: Dict[str, str] = Field(
        default_factory=dict
    )

    required_attributes: List[str] = Field(
        default_factory=list
    )

    clarification_required: bool = Field(
        default=False
    )

    missing_information: List[str] = Field(
        default_factory=list
    )

    clarification_questions: List[str] = Field(
        default_factory=list
    )

    confidence: float = Field(
        default=1.0
    )

    discovery_prompt: str = Field(
        default="",
        description="Detailed, self-contained instruction for discovery workers "
                    "(web/LinkedIn/API). Should be executable without further reasoning."
    )


# ==========================================================
# COMPANY IDENTITY
# ==========================================================

class CompanyIdentity(BaseModel):

    name: str

    website: Optional[str] = None


# ==========================================================
# RAW EVIDENCE
# ==========================================================

class RawEvidence(BaseModel):

    source: str

    source_type: str

    url: Optional[str] = None

    title: str

    metadata: Dict[str, str] = Field(
        default_factory=dict
    )

    content: str

    confidence: float = 1.0


# ==========================================================
# FACTUAL PROFILE
# ==========================================================

class CompanyFacts(BaseModel):

    industry: Optional[str] = None

    revenue: Optional[str] = None

    employee_count: Optional[int] = None

    founding_year: Optional[str] = None

    headquarters: Optional[str] = None

    countries: List[str] = Field(default_factory=list)

    products: List[str] = Field(default_factory=list)

    services: List[str] = Field(default_factory=list)

    technologies: List[str] = Field(default_factory=list)

    business_model: Optional[str] = None

    current_clients: List[str] = Field(default_factory=list)

    sales_contact_details: Optional[str] = None


# ==========================================================
# SEMANTIC PROFILE
# ==========================================================

class SemanticProfile(BaseModel):

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


# ==========================================================
# COMPLETE COMPANY PROFILE
# ==========================================================

class CompanyProfile(BaseModel):

    identity: CompanyIdentity

    raw_evidence: List[RawEvidence] = Field(
        default_factory=list
    )

    facts: CompanyFacts = Field(
        default_factory=CompanyFacts
    )

    semantic_profile: SemanticProfile = Field(
        default_factory=SemanticProfile
    )

    metadata: Dict[str, str] = Field(
        default_factory=dict
    )


# ==========================================================
# VAULT
# ==========================================================

class CompanyVault(BaseModel):

    companies: Dict[str, CompanyProfile] = Field(
        default_factory=dict
    )


# ==========================================================
# AI ANALYSIS
# ==========================================================

class CompanyAnalysis(BaseModel):

    facts: CompanyFacts

    semantic_profile: SemanticProfile