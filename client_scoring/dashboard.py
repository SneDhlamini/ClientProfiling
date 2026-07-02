import os
from datetime import datetime
from html import escape

from models.schemas import SearchSpecification

OUTPUT_DIR = os.path.join("client_scoring", "output")


def generate_dashboard(scored_companies, search_spec: SearchSpecification, output_dir: str = OUTPUT_DIR) -> str:
    """
    Renders scored companies (list of (CompanyProfile, score) tuples,
    highest score first) into an interactive HTML dashboard, plus a
    separate stylesheet you can freely edit. Returns the path to the
    generated HTML file.
    """
    os.makedirs(output_dir, exist_ok=True)

    html_path = os.path.join(output_dir, "dashboard.html")
    css_path = os.path.join(output_dir, "dashboard.css")

    _write_css_if_missing(css_path)

    cards_html = "\n".join(
        _render_card(company, score, rank + 1)
        for rank, (company, score) in enumerate(scored_companies)
    )

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Client Scoring Dashboard</title>
<link rel="stylesheet" href="dashboard.css">
</head>
<body>
  <header class="dashboard-header">
    <h1>Client Scoring Dashboard</h1>
    <p class="query">Search: <strong>{escape(search_spec.objective)}</strong></p>
    <p class="meta">Generated {generated_at} &middot; {len(scored_companies)} companies scored</p>
  </header>

  <div class="controls">
    <input type="text" id="filterInput" placeholder="Filter by company name or evidence content...">
    <div class="sort-buttons">
      <button data-sort="score" class="active">Sort by Score</button>
      <button data-sort="evidence">Sort by Evidence</button>
      <button data-sort="name">Sort by Name</button>
    </div>
  </div>

  <main id="cardGrid" class="card-grid">
    {cards_html if cards_html else '<p class="empty-state">No companies to show.</p>'}
  </main>

  <script>
{_JS}
  </script>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


def _render_card(company, score, rank) -> str:
    website = company.identity.website or "#"
    website_label = company.identity.website or "No website found"
    score_pct = round(score * 100)

    evidence_html = "\n".join(
        f"""<div class="evidence-item">
              <div class="evidence-title">{escape(evidence.title)} <span class="evidence-source">({escape(evidence.source)})</span></div>
              <div class="evidence-snippet">{escape(evidence.content[:300])}{'...' if len(evidence.content) > 300 else ''}</div>
              <a class="evidence-link" href="{escape(evidence.url or '#')}" target="_blank" rel="noopener">source</a>
            </div>"""
        for evidence in company.raw_evidence[:10]
    )

    return f"""
    <article class="client-card" data-name="{escape(company.identity.name.lower())}"
             data-score="{score}" data-evidence="{len(company.raw_evidence)}">
      <div class="card-rank">#{rank}</div>
      <h2 class="card-title">{escape(company.identity.name)}</h2>
      <a class="card-website" href="{escape(website)}" target="_blank" rel="noopener">{escape(website_label)}</a>
      <div class="score-bar-track">
        <div class="score-bar-fill" style="width:{score_pct}%"></div>
      </div>
      <div class="card-stats">
        <span>Match score: <strong>{score_pct}%</strong></span>
        <span>Evidence: <strong>{len(company.raw_evidence)}</strong></span>
      </div>
      <button class="toggle-evidence">Show evidence</button>
      <div class="evidence-list" hidden>
        {evidence_html if evidence_html else '<p class="no-evidence">No evidence collected.</p>'}
      </div>
    </article>
    """


_JS = """
const grid = document.getElementById('cardGrid');
const cards = Array.from(grid.querySelectorAll('.client-card'));

const filterInput = document.getElementById('filterInput');
if (filterInput) {
  filterInput.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    cards.forEach(card => {
      const haystack = card.dataset.name + ' ' + card.innerText.toLowerCase();
      card.style.display = haystack.includes(term) ? '' : 'none';
    });
  });
}

document.querySelectorAll('.sort-buttons button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.sort-buttons button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const key = btn.dataset.sort;
    const sorted = [...cards].sort((a, b) => {
      if (key === 'name') return a.dataset.name.localeCompare(b.dataset.name);
      return parseFloat(b.dataset[key]) - parseFloat(a.dataset[key]);
    });
    sorted.forEach(card => grid.appendChild(card));
  });
});

grid.addEventListener('click', (e) => {
  if (e.target.classList.contains('toggle-evidence')) {
    const list = e.target.nextElementSibling;
    const isHidden = list.hasAttribute('hidden');
    if (isHidden) {
      list.removeAttribute('hidden');
      e.target.textContent = 'Hide evidence';
    } else {
      list.setAttribute('hidden', '');
      e.target.textContent = 'Show evidence';
    }
  }
});
"""


def _write_css_if_missing(css_path: str):
    """
    Only writes a starter stylesheet the first time - if you've already
    customized dashboard.css, re-running the pipeline won't overwrite it.
    Delete the file yourself if you want a fresh starting point.
    """
    if os.path.exists(css_path):
        return

    css = """:root {
  --bg: #0f1115;
  --card-bg: #1a1d24;
  --text: #e8e8e8;
  --muted: #9a9ea6;
  --accent: #4f9dff;
  --accent-2: #34d399;
  --border: #2a2e37;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  padding: 2rem;
}

.dashboard-header h1 {
  margin: 0 0 0.25rem 0;
}

.dashboard-header .query {
  color: var(--accent);
  margin: 0.25rem 0;
}

.dashboard-header .meta {
  color: var(--muted);
  font-size: 0.9rem;
  margin: 0 0 1.5rem 0;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1.5rem;
}

#filterInput {
  flex: 1;
  min-width: 220px;
  padding: 0.6rem 0.9rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text);
}

.sort-buttons button {
  padding: 0.5rem 0.9rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--muted);
  cursor: pointer;
}

.sort-buttons button.active {
  color: var(--bg);
  background: var(--accent);
  border-color: var(--accent);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.25rem;
}

.client-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.25rem;
  position: relative;
}

.card-rank {
  position: absolute;
  top: 1rem;
  right: 1rem;
  color: var(--muted);
  font-size: 0.85rem;
}

.card-title {
  margin: 0 1.5rem 0.25rem 0;
  font-size: 1.1rem;
}

.card-website {
  color: var(--accent);
  font-size: 0.85rem;
  text-decoration: none;
  word-break: break-all;
}

.score-bar-track {
  height: 6px;
  background: var(--border);
  border-radius: 4px;
  margin: 0.9rem 0 0.5rem 0;
  overflow: hidden;
}

.score-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
}

.card-stats {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  color: var(--muted);
  margin-bottom: 0.75rem;
}

.toggle-evidence {
  width: 100%;
  padding: 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  cursor: pointer;
}

.evidence-list {
  margin-top: 0.75rem;
  max-height: 260px;
  overflow-y: auto;
  border-top: 1px solid var(--border);
  padding-top: 0.75rem;
}

.evidence-item {
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
}

.evidence-title {
  font-weight: 600;
}

.evidence-source {
  color: var(--muted);
  font-weight: 400;
}

.evidence-snippet {
  color: var(--muted);
  margin: 0.2rem 0;
}

.evidence-link {
  color: var(--accent);
  font-size: 0.8rem;
}

.no-evidence, .empty-state {
  color: var(--muted);
  font-size: 0.85rem;
}
"""
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(css)


# testing
if __name__ == "__main__":
    from company_vault.vault import CompanyVaultManager
    from models.schemas import RawEvidence
    from client_scoring.scorer import ClientScorer

    vault = CompanyVaultManager()

    vault.add_company("Strong Match Co")
    vault.get_company("Strong Match Co").identity.website = "https://strongmatch.example.com"
    vault.get_company("Strong Match Co").raw_evidence.append(
        RawEvidence(
            source="WebWorker", source_type="website", url="https://strongmatch.example.com/about",
            title="About", content="We provide AI consulting and manufacturing automation services in South Africa.",
        )
    )

    vault.add_company("Weak Match Co")
    vault.get_company("Weak Match Co").raw_evidence.append(
        RawEvidence(
            source="WebWorker", source_type="website", url="https://weakmatch.example.com",
            title="Home", content="We sell furniture and home decor online.",
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
    ranked = scorer.score_all(vault, search_spec)

    path = generate_dashboard(ranked, search_spec)
    print(f"Dashboard written to {path}")