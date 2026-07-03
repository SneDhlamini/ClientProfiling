import json
from pathlib import Path
from datetime import datetime

from models.schemas import SearchSpecification


class DashboardGenerator:
    """
    Generates an interactive HTML dashboard.

    Responsibilities:
        • Convert scored companies into JSON
        • Inject JSON into dashboard.html
        • Save finished dashboard into output/
    """

    def __init__(self):

        self.template = (
            Path(__file__).parent
            / "dashboard.html"
        )

        self.output_folder = (
            Path(__file__).parent
            / "output"
        )

        self.output_folder.mkdir(exist_ok=True)

        self.output_file = (
            self.output_folder
            / "dashboard.html"
        )

    # --------------------------------------------------------

    def generate(
        self,
        scored_companies,
        search_spec: SearchSpecification,
    ) -> str:

        company_json = self._prepare_company_data(
            scored_companies
        )

        search_json = self._prepare_search_data(
            search_spec,
            len(scored_companies)
        )

        with open(
            self.template,
            "r",
            encoding="utf-8"
        ) as f:

            html = f.read()

        html = html.replace(
            "__COMPANY_DATA__",
            json.dumps(
                company_json,
                indent=4
            )
        )

        html = html.replace(
            "__SEARCH_DATA__",
            json.dumps(
                search_json,
                indent=4
            )
        )

        with open(
            self.output_file,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(html)

        return str(self.output_file)

    # --------------------------------------------------------

    def _prepare_search_data(
        self,
        search_spec,
        total_companies,
    ):

        return {

            "query": search_spec.objective,

            "intent": search_spec.intent,

            "generated": datetime.now().strftime(
                "%Y-%m-%d %H:%M"
            ),

            "companies": total_companies,

            "constraints": search_spec.constraints

        }

    # --------------------------------------------------------

    def _prepare_company_data(
        self,
        scored_companies,
    ):

        companies = []

        for rank, result in enumerate(
            scored_companies,
            start=1
        ):

            company = result["company"]

            companies.append({

                "rank": rank,

                "name": company.identity.name,

                "website": company.identity.website,

                "industry": company.facts.industry,

                "employees": company.facts.employee_count,

                "revenue": company.facts.revenue,

                "headquarters": company.facts.headquarters,

                "countries": company.facts.countries,

                "products": company.facts.products,

                "services": company.facts.services,

                "technologies": company.facts.technologies,

                "customers": company.facts.current_clients,

                "business_model": company.facts.business_model,

                "semantic_profile": {

                    "ai_readiness":
                    company.semantic_profile.ai_readiness,

                    "innovation_level":
                    company.semantic_profile.innovation_level,

                    "growth_stage":
                    company.semantic_profile.growth_stage,

                    "business_health":
                    company.semantic_profile.business_health,

                    "enterprise_readiness":
                    company.semantic_profile.enterprise_readiness,

                    "partnership_potential":
                    company.semantic_profile.partnership_potential,

                    "investment_capacity":
                    company.semantic_profile.investment_capacity,

                    "ai_opportunities":
                    company.semantic_profile.ai_opportunities,

                    "automation_opportunities":
                    company.semantic_profile.automation_opportunities,

                    "strategic_priorities":
                    company.semantic_profile.strategic_priorities,

                    "risk_factors":
                    company.semantic_profile.risk_factors,

                },

                "scores": {

                    "overall":
                    result["final_score"],

                    "business":
                    result["business_score"],

                    "semantic":
                    result["semantic_score"],

                    "technology":
                    result["technology_score"],

                    "evidence":
                    result["evidence_score"]

                },

                "explanation":
                result["explanation"],

                "evidence": [

                    {

                        "title": e.title,

                        "source": e.source,

                        "type": e.source_type,

                        "url": e.url,

                        "confidence": e.confidence,

                        "content": e.content

                    }

                    for e in company.raw_evidence

                ]

            })

        return companies