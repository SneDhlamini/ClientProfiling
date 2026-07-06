"""
app.py

Interactive version of main.py. Instead of hardcoding SEARCH_QUERY and
running once from the command line, this starts a small local web
server. Open it in your browser and you get the dashboard with a search
box at the top - type a new prompt, hit Search, and the whole pipeline
(intent analysis -> discovery -> profiling -> scoring -> dashboard)
reruns and the page updates with the new results.

Run with:
    python app.py

Then open:
    http://127.0.0.1:5000

Requires Flask (pip install flask) in addition to everything main.py
already needs.
"""

from flask import Flask, request

from prompt.prompt import analyze_intent
from company_vault.vault import CompanyVaultManager

from company_discovery.web_worker import WebWorker
from company_discovery.linkedin_worker import LinkedInWorker
from company_discovery.wikidata_worker import WikidataWorker

from company_profiling.profiler import CompanyProfiler

from client_scoring.scorer import ClientScorer
from client_scoring.dashboard import DashboardGenerator

app = Flask(__name__)
dashboard_generator = DashboardGenerator()

# Kept in memory so GET / can re-render the last result set without
# rerunning the whole pipeline.
_last_ranked_companies = []
_last_search_spec = None


def run_pipeline(user_prompt: str):
    """
    Same steps as main.py's main(), just factored out so both the CLI
    script and the Flask route can call it.
    """
    search_spec = analyze_intent(user_prompt)

    if search_spec.clarification_required:
        return [], search_spec

    vault = CompanyVaultManager()

    WebWorker().discover(search_spec, vault)
    LinkedInWorker().discover(search_spec, vault)
    WikidataWorker().enrich(vault)

    profiler = CompanyProfiler()
    for company in vault.get_all_companies():
        if not company.raw_evidence:
            continue
        try:
            profiler.profile(company, vault)
        except Exception as e:
            print(f"Profiling error for {company.identity.name}: {e}")

    scorer = ClientScorer()
    ranked_companies = scorer.score_all(vault, search_spec)

    return ranked_companies, search_spec


@app.route("/", methods=["GET"])
def index():
    if _last_search_spec is None:
        # Nothing searched yet - show an empty dashboard with just the search box.
        from models.schemas import SearchSpecification

        placeholder_spec = SearchSpecification(
            intent="",
            objective="Type a prompt to start searching for companies.",
            constraints={},
            required_attributes=[],
            clarification_required=False,
        )
        return dashboard_generator.render_html([], placeholder_spec, interactive=True)

    return dashboard_generator.render_html(_last_ranked_companies, _last_search_spec, interactive=True)


@app.route("/search", methods=["POST"])
def search():
    global _last_ranked_companies, _last_search_spec

    user_prompt = request.form.get("prompt", "").strip()
    if not user_prompt:
        return "Prompt is required", 400

    ranked_companies, search_spec = run_pipeline(user_prompt)

    if search_spec.clarification_required:
        # Surface the clarification questions as the "objective" text so
        # the user sees them without needing a separate UI state.
        questions = " / ".join(search_spec.clarification_questions) or "Please provide more detail."
        search_spec.objective = f"I need more information: {questions}"

    _last_ranked_companies = ranked_companies
    _last_search_spec = search_spec

    return dashboard_generator.render_html(ranked_companies, search_spec, interactive=True)


if __name__ == "__main__":
    app.run(debug=True)