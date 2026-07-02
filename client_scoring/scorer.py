import re

from models.schemas import SearchSpecification, CompanyProfile
from company_vault.vault import CompanyVaultManager

# Common words stripped out before keyword matching so they don't dilute
# the score (nearly every search mentions "companies" and "find", so
# matching on those tells you nothing about relevance).
STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "this", "are", "was",
    "were", "have", "has", "will", "find", "companies", "company", "any",
    "all", "into", "their", "them", "such", "also", "other", "using",
    "region", "industry", "objective", "reference",
}

# Final score = KEYWORD_WEIGHT * keyword_match_score + EVIDENCE_WEIGHT * evidence_volume_score
KEYWORD_WEIGHT = 0.7
EVIDENCE_WEIGHT = 0.3

# Evidence volume score saturates at this many evidence records, so a
# company with a huge pile of scraped pages doesn't win purely on volume.
EVIDENCE_SATURATION = 10


class ClientScorer:
    """
    Ranks companies already in the vault by how well their collected
    evidence matches the user's search intent. Entirely local - no LLM
    or external API calls, so it costs nothing to run and never fails
    on rate limits or schema validation.
    """

    def score_all(self, vault: CompanyVaultManager, search_spec: SearchSpecification):
        """
        Returns a list of (CompanyProfile, score) tuples, sorted by
        score descending. Score is a float between 0.0 and 1.0.
        """
        keywords = self._extract_keywords(search_spec)

        scored = [
            (company, self._score_company(company, keywords))
            for company in vault.get_all_companies()
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def _extract_keywords(self, search_spec: SearchSpecification) -> set[str]:
        text_parts = [search_spec.objective, search_spec.discovery_prompt]
        text_parts += list(search_spec.constraints.values())
        text_parts += search_spec.required_attributes

        blob = " ".join(part for part in text_parts if part).lower()
        words = re.findall(r"[a-zA-Z]{3,}", blob)

        return {word for word in words if word not in STOPWORDS}

    def _score_company(self, company: CompanyProfile, keywords: set[str]) -> float:
        if not keywords:
            return 0.0

        combined_text = " ".join(
            evidence.content for evidence in company.raw_evidence if evidence.content
        ).lower()

        if not combined_text:
            return 0.0

        matched = sum(1 for keyword in keywords if keyword in combined_text)
        keyword_score = matched / len(keywords)

        evidence_score = min(len(company.raw_evidence) / EVIDENCE_SATURATION, 1.0)

        score = (KEYWORD_WEIGHT * keyword_score) + (EVIDENCE_WEIGHT * evidence_score)
        return round(score, 4)


# testing
if __name__ == "__main__":
    from models.schemas import CompanyIdentity, RawEvidence

    vault = CompanyVaultManager()

    vault.add_company("Strong Match Co")
    vault.get_company("Strong Match Co").raw_evidence.append(
        RawEvidence(
            source="test", source_type="website", title="Home",
            content="We provide AI consulting and manufacturing automation services in South Africa.",
        )
    )

    vault.add_company("Weak Match Co")
    vault.get_company("Weak Match Co").raw_evidence.append(
        RawEvidence(
            source="test", source_type="website", title="Home",
            content="We sell furniture and home decor online.",
        )
    )

    search_spec = SearchSpecification(
        intent="Company Discovery",
        objective="Find AI consulting companies in South Africa",
        constraints={"industry": "AI Consulting", "region": "South Africa"},
        required_attributes=["technologies", "AI initiatives"],
        clarification_required=False,
        discovery_prompt="Find companies offering AI consulting and manufacturing automation in South Africa.",
    )

    scorer = ClientScorer()
    for company, score in scorer.score_all(vault, search_spec):
        print(f"{company.identity.name}: {score}")