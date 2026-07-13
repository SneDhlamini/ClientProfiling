
import os
import html
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate

from prompt.prompt import llm
from models.schemas import SearchSpecification, CompanyProfile

WHY_SELECTED_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
            This company already passed the match threshold and was
            selected as a strong result for this search. In 2-3 concise
            sentences, explain why it's a good fit.

            Only give SUPPORTING reasons. Never mention gaps, missing
            data, weak/thin evidence, location mismatches, or anything
            that could make the company seem like a poor fit - if a
            detail doesn't support the match, leave it out entirely
            rather than raising it. Do not hedge with words like "may",
            "unclear", "somewhat", "not a strong match", or similar. Write
            with confidence about the reasons that DO support the match.

            Ground every sentence ONLY in the facts, semantic profile and
            score breakdown provided to you - never invent details that
            aren't present in that data.

            Write directly to the reader (the person who ran the search),
            not about "the evidence". Do not repeat the company name more
            than once. Do not use bullet points - plain prose only.
            """,
        ),
        (
            "human",
            """
            Search objective: {objective}
            Search constraints: {constraints}

            Company: {name}

            Facts:
            {facts}

            Semantic profile:
            {semantic_profile}

            Score breakdown:
            {breakdown}
            """,
        ),
    ]
)

_why_chain = WHY_SELECTED_PROMPT | llm


class DashboardGenerator:
    # Companies scoring  dashboard
    
    MIN_MATCH_SCORE = 0.55

    def __init__(self, output_dir: str = "dashboards", min_match_score: float = MIN_MATCH_SCORE):
        self.output_dir = output_dir
        self.min_match_score = min_match_score

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def generate(self, ranked_companies, search_spec: SearchSpecification) -> str:
        
        #Writes the dashboard to disk and returns the file path.
        
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.output_dir, f"dashboard_{timestamp}.html")

        html_content = self.render_html(ranked_companies, search_spec)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return path

    def render_html(self, ranked_companies, search_spec: SearchSpecification, interactive: bool = False) -> str:
        
        strong_matches = [
            (company, score, breakdown)
            for company, score, breakdown in ranked_companies
            if score >= self.min_match_score
        ]

        cards = "".join(
            self._render_company_card(company, score, breakdown, search_spec)
            for company, score, breakdown in strong_matches
        )

        if not strong_matches:
            cards = '<p class="empty">No companies met the match threshold for this search. Try broadening the prompt.</p>'

        search_box = self._render_search_box(search_spec) if interactive else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Company Discovery Dashboard</title>
<style>
{self._css()}
</style>
</head>
<body>
<div class="page">
  <header>
    <h1>Client Profiling Dashboard</h1>
    <p class="subtitle">{html.escape(search_spec.objective or "")}</p>
    {self._render_meta(search_spec)}
  </header>
  {search_box}
  <main class="grid">
    {cards}
  </main>
  <footer>
    <p>Generated {html.escape(datetime.now().strftime("%Y-%m-%d %H:%M"))} &middot; {len(strong_matches)} companies</p>
  </footer>
</div>
{self._js() if interactive else ""}
</body>
</html>"""

    
    # LLM explanation
    
    def why_selected(self, company: CompanyProfile, breakdown: dict, search_spec: SearchSpecification) -> str:
        facts_text = self._format_model(company.facts)
        semantic_text = self._format_model(company.semantic_profile)
        breakdown_text = "\n".join(f"- {k}: {v}" for k, v in breakdown.items())

        try:
            response = _why_chain.invoke(
                {
                    "objective": search_spec.objective,
                    "constraints": search_spec.constraints,
                    "name": company.identity.name,
                    "facts": facts_text or "No structured facts extracted.",
                    "semantic_profile": semantic_text or "No semantic profile inferred.",
                    "breakdown": breakdown_text,
                }
            )
            return response.content.strip()
        except Exception as e:
            return f"(Explanation unavailable - {e})"

    # rendering helpers
    
    def _render_company_card(self, company: CompanyProfile, score: float, breakdown: dict, search_spec: SearchSpecification) -> str:
        name = html.escape(company.identity.name)
        website = company.identity.website
        website_html = (
            f'<a class="website" href="{html.escape(website)}" target="_blank" rel="noopener">{html.escape(website)}</a>'
            if website
            else '<span class="website missing">No website found</span>'
        )

        why = html.escape(self.why_selected(company, breakdown, search_spec))
        pct = round(score * 100)
        contact_html = self._render_contact(company, website)

        facts_html = self._render_kv_block(company.facts.model_dump(exclude_none=True))
        semantic_html = self._render_kv_block(company.semantic_profile.model_dump(exclude_none=True))
        sources_html = "".join(self._render_source_item(ev) for ev in company.raw_evidence)

        return f"""
        <article class="card">
          <div class="card-header">
            <h2>{name}</h2>
            <div class="score" style="--pct:{pct}">{pct}%</div>
          </div>
          {website_html}
          <p class="why">{why}</p>
          {contact_html}
          <details>
            <summary>Facts &amp; profile ({len(company.raw_evidence)} sources)</summary>
            <div class="details-grid">
              <div>
                <h3>Facts</h3>
                {facts_html or "<p class='muted'>No facts extracted.</p>"}
              </div>
              <div>
                <h3>Semantic profile</h3>
                {semantic_html or "<p class='muted'>No semantic profile.</p>"}
              </div>
            </div>
            <h3>Sources</h3>
            <ul class="sources">{sources_html or "<li class='muted'>No sources.</li>"}</ul>
          </details>
        </article>
        """

    def _render_contact(self, company: CompanyProfile, website: str | None) -> str:
        details = company.facts.sales_contact_details
        if details:
            return f'<p class="contact"><span class="contact-label">Contact</span> {html.escape(details)}</p>'
        if website:
            return f'<p class="contact"><span class="contact-label">Contact</span> No direct contact found - reach out via <a href="{html.escape(website)}" target="_blank" rel="noopener">{html.escape(website)}</a></p>'
        return '<p class="contact muted"><span class="contact-label">Contact</span> No contact details found.</p>'

    def _render_source_item(self, evidence) -> str:
        source_name = html.escape(evidence.source)
        if evidence.url:
            link = html.escape(evidence.url)
            return f'<li><span class="src-name">{source_name}</span> - <a href="{link}" target="_blank" rel="noopener">source</a></li>'
        return f'<li><span class="src-name">{source_name}</span></li>'

    def _render_kv_block(self, data: dict) -> str:
        rows = []
        for key, value in data.items():
            label = html.escape(key.replace("_", " ").title())
            if isinstance(value, list):
                if not value:
                    continue
                value_str = ", ".join(str(v) for v in value)
            else:
                value_str = str(value)
            rows.append(f"<div class='kv'><span class='k'>{label}</span><span class='v'>{html.escape(value_str)}</span></div>")
        return "".join(rows)

    def _render_meta(self, search_spec: SearchSpecification) -> str:
        if not search_spec.constraints:
            return ""
        chips = "".join(
            f'<span class="chip">{html.escape(k)}: {html.escape(v)}</span>'
            for k, v in search_spec.constraints.items()
        )
        return f'<div class="chips">{chips}</div>'

    def _render_search_box(self, search_spec: SearchSpecification) -> str:
        return f"""
        <form class="search-box" id="search-form">
          <input type="text" name="prompt" placeholder="Search for companies... e.g. 'Find AI consulting companies in South Africa'" required>
          <button type="submit">Search</button>
        </form>
        <div id="search-status"></div>
        """

    def _format_model(self, model) -> str:
        data = model.model_dump(exclude_none=True)
        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                if not value:
                    continue
                value = ", ".join(str(v) for v in value)
            lines.append(f"{key.replace('_', ' ').title()}: {value}")
        return "\n".join(lines)

    # static assets


    def _css(self) -> str:
        return """
        :root {
          --bg: #0f1115; --panel: #171a21; --border: #262b36;
          --text: #e7e9ee; --muted: #8b93a3; --accent: #7c9eff; --good: #4ade80;
        }
        * { box-sizing: border-box; }
        body { margin:0; background:var(--bg); color:var(--text); font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
        .page { max-width: 1100px; margin: 0 auto; padding: 40px 24px 80px; }
        header h1 { margin: 0 0 4px; font-size: 28px; }
        .subtitle { color: var(--muted); margin: 0 0 12px; }
        .chips { display:flex; flex-wrap:wrap; gap:8px; margin-bottom: 20px; }
        .chip { background: var(--panel); border:1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 13px; color: var(--muted); }
        .search-box { display:flex; gap:8px; margin: 20px 0 32px; }
        .search-box input { flex:1; padding: 12px 14px; border-radius: 8px; border:1px solid var(--border); background: var(--panel); color: var(--text); font-size:15px; }
        .search-box button { padding: 12px 20px; border-radius: 8px; border:none; background: var(--accent); color:#0f1115; font-weight:600; cursor:pointer; }
        #search-status { color: var(--muted); font-size: 13px; margin-bottom: 12px; min-height: 18px; }
        .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 18px; }
        .card { background: var(--panel); border:1px solid var(--border); border-radius: 14px; padding: 20px; }
        .card-header { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
        .card-header h2 { margin:0; font-size: 18px; }
        .score { font-weight:700; font-size:14px; background: conic-gradient(var(--good) calc(var(--pct)*1%), var(--border) 0); width:44px; height:44px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
        .score::after { content:''; }
        .website { color: var(--accent); font-size: 13px; text-decoration:none; word-break: break-all; }
        .website.missing { color: var(--muted); }
        .why { color: var(--text); font-size: 14px; line-height:1.5; margin: 12px 0; }
        .contact { font-size: 13px; color: var(--text); background: rgba(124,158,255,0.08); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; margin: 0 0 12px; }
        .contact-label { color: var(--accent); font-weight:600; margin-right: 6px; }
        .contact a { color: var(--accent); }
        .contact.muted { color: var(--muted); background: transparent; }
        details { margin-top: 8px; }
        summary { cursor:pointer; color: var(--muted); font-size: 13px; }
        .details-grid { display:grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 12px 0; }
        .details-grid h3 { font-size: 12px; text-transform:uppercase; letter-spacing:.04em; color: var(--muted); margin: 0 0 8px; }
        .kv { display:flex; justify-content:space-between; gap:8px; font-size: 13px; padding: 4px 0; border-bottom: 1px solid var(--border); }
        .kv .k { color: var(--muted); }
        .kv .v { text-align:right; }
        .sources { list-style:none; padding:0; margin: 8px 0 0; font-size: 13px; }
        .sources li { padding: 4px 0; color: var(--muted); }
        .sources a { color: var(--accent); }
        .muted { color: var(--muted); font-size: 13px; }
        .empty { color: var(--muted); }
        footer { color: var(--muted); font-size: 12px; margin-top: 40px; text-align:center; }
        """

    def _js(self) -> str:
        return """
        <script>
        const form = document.getElementById('search-form');
        const status = document.getElementById('search-status');
        form.addEventListener('submit', async (e) => {
          e.preventDefault();
          const prompt = form.prompt.value.trim();
          if (!prompt) return;
          status.textContent = 'Searching... this can take a minute (discovery + profiling + scoring).';
          form.querySelector('button').disabled = true;
          try {
            const res = await fetch('/search', {
              method: 'POST',
              headers: {'Content-Type': 'application/x-www-form-urlencoded'},
              body: 'prompt=' + encodeURIComponent(prompt)
            });
            if (!res.ok) throw new Error('Search failed: ' + res.status);
            const newHtml = await res.text();
            document.open(); document.write(newHtml); document.close();
          } catch (err) {
            status.textContent = err.message;
            form.querySelector('button').disabled = false;
          }
        });
        </script>
        """
