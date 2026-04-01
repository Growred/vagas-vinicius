#!/usr/bin/env python3
"""
Busca vagas no LinkedIn relevantes para o perfil do Vinicius
e gera uma pagina HTML estatica com as vagas classificadas.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import quote
import time
import json
import os
import re

# ============================================================
# CONFIGURACAO DO PERFIL
# ============================================================

SEARCH_QUERIES = [
    "gerente jurídico",
    "head jurídico",
    "diretor jurídico",
    "coordenador jurídico",
    "gerente regulatório",
    "gerente contratos",
    "jurídico telecom",
    "jurídico telecomunicações",
    "legal manager",
    "legal counsel telecom",
    "antitruste",
    "concorrencial",
]

LOCATION = "Brazil"

# Palavras que EXCLUEM a vaga sumariamente
DENYLIST = [
    "junior", "júnior", "jr",
    "pleno",
    "compliance",
    "auxiliar",
    "assistente",
    "analista",
]

# Palavras-chave que indicam FIT com o perfil do Vinicius
FIT_KEYWORDS = [
    # Cargo
    "gerente jurídico", "gerente juridico", "head jurídico", "head juridico",
    "diretor jurídico", "diretor juridico", "coordenador jurídico",
    "coordenador juridico", "legal manager", "legal director", "legal head",
    "head of legal", "gerente legal",
    # Regulatorio / Telecom
    "regulatório", "regulatorio", "telecom", "telecomunicações",
    "telecomunicacoes", "anatel", "agência reguladora", "agencia reguladora",
    "regulatory",
    # Contratos
    "contratos", "contract", "negociação contratual", "gestão contratual",
    "gestao contratual",
    # Concorrencial / Antitruste
    "concorrencial", "antitruste", "antitrust", "cade", "defesa da concorrência",
    "defesa da concorrencia", "competition law", "merger control",
]

# Palavras que indicam relevancia media (juridico em geral)
RELATED_KEYWORDS = [
    "jurídico", "juridico", "legal", "advogado", "lawyer", "counsel",
    "contencioso", "litigation", "societário", "societario", "corporate",
    "m&a", "fusões", "aquisições",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ============================================================
# SCRAPING DO LINKEDIN
# ============================================================

def fetch_linkedin_jobs(query, location="Brazil", num_pages=2):
    """Busca vagas no LinkedIn usando a API publica de guest."""
    jobs = []
    for page in range(num_pages):
        start = page * 25
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={quote(query)}"
            f"&location={quote(location)}"
            f"&f_TPR=r86400"  # ultimas 24 horas
            f"&start={start}"
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"  [WARN] Status {resp.status_code} para query '{query}' page {page}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="base-card")

            for card in cards:
                job = parse_linkedin_card(card)
                if job:
                    jobs.append(job)

            print(f"  [OK] '{query}' page {page}: {len(cards)} vagas encontradas")

        except Exception as e:
            print(f"  [ERR] Erro buscando '{query}': {e}")

        time.sleep(1.5)  # rate limiting

    return jobs


def parse_linkedin_card(card):
    """Extrai informacoes de um card de vaga do LinkedIn."""
    try:
        title_el = card.find("h3", class_="base-search-card__title")
        company_el = card.find("h4", class_="base-search-card__subtitle")
        location_el = card.find("span", class_="job-search-card__location")
        link_el = card.find("a", class_="base-card__full-link")
        time_el = card.find("time")

        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            return None

        company = company_el.get_text(strip=True) if company_el else "N/A"
        location = location_el.get_text(strip=True) if location_el else "N/A"
        link = link_el["href"].split("?")[0] if link_el and link_el.get("href") else "#"
        posted = time_el.get_text(strip=True) if time_el else "Recente"

        return {
            "title": title,
            "company": company,
            "location": location,
            "link": link,
            "posted": posted,
            "source": "LinkedIn",
        }
    except Exception:
        return None


# ============================================================
# CLASSIFICACAO
# ============================================================

def classify_job(job):
    """
    Classifica a vaga como 'fit' ou 'other'.
    Retorna (categoria, score).
    """
    text = f"{job['title']} {job.get('company', '')}".lower()
    text = normalize(text)

    fit_score = 0
    for kw in FIT_KEYWORDS:
        if normalize(kw) in text:
            fit_score += 2

    related_score = 0
    for kw in RELATED_KEYWORDS:
        if normalize(kw) in text:
            related_score += 1

    total = fit_score + related_score

    if fit_score >= 2:
        return "fit", total
    elif total >= 2:
        return "fit", total
    else:
        return "other", total


def normalize(text):
    """Remove acentos e normaliza texto para comparacao."""
    replacements = {
        "á": "a", "à": "a", "ã": "a", "â": "a",
        "é": "e", "ê": "e",
        "í": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u", "ü": "u",
        "ç": "c",
    }
    text = text.lower()
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


# ============================================================
# DEDUPLICACAO
# ============================================================

def deduplicate(jobs):
    """Remove vagas duplicadas baseado no link ou titulo+empresa."""
    seen = set()
    unique = []
    for job in jobs:
        key = job["link"] if job["link"] != "#" else f"{job['title']}|{job['company']}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


# ============================================================
# GERACAO HTML
# ============================================================

def generate_html(fit_jobs, other_jobs, date_str):
    """Gera a pagina HTML com as vagas classificadas."""

    def job_card(job):
        score_badge = ""
        return f"""
        <div class="job-card">
            <div class="job-header">
                <h3 class="job-title">
                    <a href="{job['link']}" target="_blank" rel="noopener">{job['title']}</a>
                </h3>
                <span class="job-source">{job['source']}</span>
            </div>
            <div class="job-details">
                <span class="job-company">{job['company']}</span>
                <span class="job-location">{job['location']}</span>
                <span class="job-posted">{job['posted']}</span>
            </div>
        </div>"""

    fit_cards = "\n".join(job_card(j) for j in fit_jobs) if fit_jobs else '<p class="empty">Nenhuma vaga com fit encontrada hoje.</p>'
    other_cards = "\n".join(job_card(j) for j in other_jobs) if other_jobs else '<p class="empty">Nenhuma outra vaga encontrada hoje.</p>'

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vagas para Vinicius</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
        }}

        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem 1rem;
        }}

        header {{
            text-align: center;
            margin-bottom: 2.5rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid #1e293b;
        }}

        header h1 {{
            font-size: 2rem;
            font-weight: 700;
            color: #f8fafc;
            margin-bottom: 0.5rem;
        }}

        header h1 span {{
            color: #38bdf8;
        }}

        .subtitle {{
            color: #94a3b8;
            font-size: 0.95rem;
        }}

        .update-date {{
            display: inline-block;
            margin-top: 0.75rem;
            background: #1e293b;
            color: #38bdf8;
            padding: 0.3rem 0.8rem;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 500;
        }}

        .section {{
            margin-bottom: 2.5rem;
        }}

        .section-header {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }}

        .section-header h2 {{
            font-size: 1.3rem;
            font-weight: 600;
        }}

        .badge {{
            background: #38bdf8;
            color: #0f172a;
            padding: 0.15rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
        }}

        .badge.other {{
            background: #475569;
            color: #e2e8f0;
        }}

        .section.fit .section-header h2 {{
            color: #38bdf8;
        }}

        .section.other-section .section-header h2 {{
            color: #94a3b8;
        }}

        .job-card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 0.75rem;
            padding: 1.2rem;
            margin-bottom: 0.75rem;
            transition: border-color 0.2s, transform 0.1s;
        }}

        .job-card:hover {{
            border-color: #38bdf8;
            transform: translateY(-1px);
        }}

        .job-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 0.6rem;
        }}

        .job-title {{
            font-size: 1.05rem;
            font-weight: 600;
            line-height: 1.3;
        }}

        .job-title a {{
            color: #f1f5f9;
            text-decoration: none;
        }}

        .job-title a:hover {{
            color: #38bdf8;
            text-decoration: underline;
        }}

        .job-source {{
            background: #0ea5e9;
            color: white;
            padding: 0.15rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.7rem;
            font-weight: 600;
            white-space: nowrap;
            flex-shrink: 0;
        }}

        .job-details {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem 1.2rem;
            font-size: 0.85rem;
            color: #94a3b8;
        }}

        .job-company {{
            font-weight: 500;
            color: #cbd5e1;
        }}

        .job-location::before {{
            content: "\\1F4CD ";
        }}

        .job-posted::before {{
            content: "\\1F553 ";
        }}

        .empty {{
            color: #64748b;
            font-style: italic;
            padding: 1.5rem;
            text-align: center;
            background: #1e293b;
            border-radius: 0.75rem;
        }}

        .profile-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            justify-content: center;
            margin-top: 0.75rem;
        }}

        .profile-tag {{
            background: #1e293b;
            border: 1px solid #334155;
            color: #94a3b8;
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
        }}

        footer {{
            text-align: center;
            padding: 2rem 0;
            border-top: 1px solid #1e293b;
            color: #475569;
            font-size: 0.8rem;
        }}

        @media (max-width: 640px) {{
            header h1 {{
                font-size: 1.5rem;
            }}
            .job-header {{
                flex-direction: column;
                gap: 0.4rem;
            }}
            .job-details {{
                flex-direction: column;
                gap: 0.3rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Vagas para <span>Vinicius</span></h1>
            <p class="subtitle">
                Gerente Juridico &bull; Regulatorio &bull; Telecom &bull; Concorrencial
            </p>
            <div class="profile-tags">
                <span class="profile-tag">Contratos</span>
                <span class="profile-tag">ANATEL</span>
                <span class="profile-tag">CADE</span>
                <span class="profile-tag">Telecom</span>
                <span class="profile-tag">Regulatorio</span>
                <span class="profile-tag">Antitruste</span>

            </div>
            <div class="update-date">Atualizado em {date_str}</div>
        </header>

        <section class="section fit">
            <div class="section-header">
                <h2>Fit de Oportunidade</h2>
                <span class="badge">{len(fit_jobs)}</span>
            </div>
            {fit_cards}
        </section>

        <section class="section other-section">
            <div class="section-header">
                <h2>Outras Coisas</h2>
                <span class="badge other">{len(other_jobs)}</span>
            </div>
            {other_cards}
        </section>

        <footer>
            <p>Atualizado automaticamente via GitHub Actions</p>
            <p style="margin-top: 0.3rem;">Fontes: LinkedIn</p>
        </footer>
    </div>
</body>
</html>"""

    return html


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("  Buscando vagas para Vinicius")
    print("=" * 60)

    all_jobs = []

    for query in SEARCH_QUERIES:
        print(f"\nBuscando: '{query}'...")
        jobs = fetch_linkedin_jobs(query, LOCATION, num_pages=2)
        all_jobs.extend(jobs)
        time.sleep(2)  # pausa entre queries

    print(f"\n--- Total bruto: {len(all_jobs)} vagas ---")

    # Deduplicar
    all_jobs = deduplicate(all_jobs)
    print(f"--- Apos deduplicacao: {len(all_jobs)} vagas ---")

    # Filtrar denylist
    before = len(all_jobs)
    all_jobs = [
        job for job in all_jobs
        if not any(normalize(word) in normalize(job["title"]) for word in DENYLIST)
    ]
    print(f"--- Apos denylist: {len(all_jobs)} vagas ({before - len(all_jobs)} removidas) ---")

    # Classificar
    fit_jobs = []
    other_jobs = []

    for job in all_jobs:
        category, score = classify_job(job)
        job["score"] = score
        if category == "fit":
            fit_jobs.append(job)
        else:
            other_jobs.append(job)

    # Ordenar por score (maior primeiro)
    fit_jobs.sort(key=lambda j: j["score"], reverse=True)
    other_jobs.sort(key=lambda j: j["score"], reverse=True)

    print(f"\n--- Fit de Oportunidade: {len(fit_jobs)} vagas ---")
    print(f"--- Outras Coisas: {len(other_jobs)} vagas ---")

    # Gerar HTML
    date_str = datetime.now().strftime("%d/%m/%Y as %H:%M")
    html = generate_html(fit_jobs, other_jobs, date_str)

    # Salvar
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)))
    output_path = os.path.join(output_dir, "index.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n[OK] Pagina gerada: {output_path}")
    print(f"[OK] {len(fit_jobs)} vagas fit + {len(other_jobs)} outras = {len(fit_jobs) + len(other_jobs)} total")


if __name__ == "__main__":
    main()
