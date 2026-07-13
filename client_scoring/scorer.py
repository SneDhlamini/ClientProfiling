"""


Deterministic (no-LLM) scoring of every company in the vault against the
original SearchSpecification.

The score is a 0.0-1.0 float built from four weighted components:

    constraint_match        - do the user's constraints actually show up
                               in this company's facts?
    attribute_completeness  - how many of the required_attributes were we
                               able to fill in?
    semantic_depth          - how much of the semantic_profile could the
                               LLM confidently fill in?
    evidence_richness       - how many sources of evidence records do we
                               have ?
No LLM,it's pure Python so it's fast, free, and
reproducible. The LLM-based "why this company was selected" explanation
lives in client_scoring/dashboard.py, which is free to use this score's
breakdown as grounding for that explanation.
"""

from models.schemas import SearchSpecification, CompanyProfile
from company_vault.vault import CompanyVaultManager

WEIGHTS = {
    "constraint_match": 0.50,
    "attribute_completeness": 0.20,
    "semantic_depth": 0.20,
    "evidence_richness": 0.10,
}


class ClientScorer:
    def score_all(self, vault: CompanyVaultManager, search_spec: SearchSpecification):
        """
        Scores every company in the vault and returns a list of
        (company, score, breakdown) tuples sorted highest-score first.
        """
        results = []
        for company in vault.get_all_companies():
            score, breakdown = self.score_company(company, search_spec)
            results.append((company, score, breakdown))

        results.sort(key=lambda item: item[1], reverse=True)
        return results

    def score_company(self, company: CompanyProfile, search_spec: SearchSpecification):
        constraint_score, matched_constraints = self._score_constraints(company, search_spec)
        attribute_score, matched_attributes, missing_attributes = self._score_attributes(company, search_spec)
        semantic_score, filled_semantic_fields = self._score_semantic_depth(company)
        evidence_score, evidence_count = self._score_evidence_richness(company)

        total = (
            constraint_score * WEIGHTS["constraint_match"]
            + attribute_score * WEIGHTS["attribute_completeness"]
            + semantic_score * WEIGHTS["semantic_depth"]
            + evidence_score * WEIGHTS["evidence_richness"]
        )
        total = round(min(max(total, 0.0), 1.0), 4)

        breakdown = {
            "constraint_match": round(constraint_score, 4),
            "matched_constraints": matched_constraints,
            "attribute_completeness": round(attribute_score, 4),
            "matched_attributes": matched_attributes,
            "missing_attributes": missing_attributes,
            "semantic_depth": round(semantic_score, 4),
            "filled_semantic_fields": filled_semantic_fields,
            "evidence_richness": round(evidence_score, 4),
            "evidence_count": evidence_count,
        }
        return total, breakdown

    # ------------------------------------------------------------------
    # constraint_match
    # ------------------------------------------------------------------
    def _score_constraints(self, company: CompanyProfile, search_spec: SearchSpecification):
        constraints = search_spec.constraints or {}
        if not constraints:
            # Nothing to match against -> don't cancel the company for it.
            return 1.0, []

        haystack = self._company_text_blob(company).lower()

        matched = []
        for key, value in constraints.items():
            if value and value.lower() in haystack:
                matched.append(key)

        return len(matched) / len(constraints), matched

    # ------------------------------------------------------------------
    # attribute_completeness
    # ------------------------------------------------------------------
    def _score_attributes(self, company: CompanyProfile, search_spec: SearchSpecification):
        required = search_spec.required_attributes or []
        if not required:
            return 1.0, [], []

        facts = company.facts
        matched, missing = [], []
        for attr in required:
            field_name = attr.strip().lower().replace(" ", "_")
            value = getattr(facts, field_name, None)
            if value:
                matched.append(attr)
            else:
                missing.append(attr)

        return len(matched) / len(required), matched, missing

    # ------------------------------------------------------------------
    # semantic_depth
    # ------------------------------------------------------------------
    def _score_semantic_depth(self, company: CompanyProfile):
        profile_dict = company.semantic_profile.model_dump()
        filled = [k for k, v in profile_dict.items() if v]
        total_fields = len(profile_dict) or 1
        return len(filled) / total_fields, filled

    # ------------------------------------------------------------------
    # evidence_richness
    # ------------------------------------------------------------------
    def _score_evidence_richness(self, company: CompanyProfile):
        count = len(company.raw_evidence)
        # 5+ independent evidence records = full score, scales linearly below that
        return min(count / 5, 1.0), count

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _company_text_blob(self, company: CompanyProfile) -> str:
        parts = [company.identity.name, company.identity.website or ""]

        facts = company.facts
        parts.append(facts.industry or "")
        parts.append(facts.headquarters or "")
        parts.append(facts.business_model or "")
        parts.extend(facts.countries)
        parts.extend(facts.products)
        parts.extend(facts.services)
        parts.extend(facts.technologies)
        parts.extend(facts.current_clients)

        for evidence in company.raw_evidence:
            parts.append(evidence.content)

        return " \n ".join(parts)
