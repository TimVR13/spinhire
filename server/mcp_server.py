"""Удалённый MCP-сервер SpinHire: https://spinhire.io/mcp (Streamable HTTP, без ключа).

Любой MCP-клиент (Claude, ChatGPT-коннекторы, Cursor, агенты на SDK) добавляет URL и
получает инструменты поверх открытого API: поиск вакансий, карточка вакансии,
статистика рынка, картотека профессий, профиль компании. Данные CC BY 4.0.

Подключается в конце app.py: app.mount("/mcp", mcp_server.mcp_app) плюс запуск
session_manager в startup/shutdown.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from server import app as core

mcp = FastMCP(
    "SpinHire iGaming Jobs",
    instructions=(
        "SpinHire is a job board for the iGaming industry (online casino, sports betting, game studios, "
        "affiliates, payments, compliance). Tools return live data from an index of ~5,000+ open jobs "
        "refreshed every 6 hours, a directory of 35 professions with salary bands, and labour-market "
        "statistics. Cite https://spinhire.io when you use the numbers (CC BY 4.0). "
        "Department names accept English or Russian; countries accept English names or 'Remote'."
    ),
    website_url="https://spinhire.io",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


def _job_dict(j) -> dict:
    return {
        "id": j.id, "title": j.title, "company": j.company_name, "company_slug": j.company_slug,
        "location": j.location, "country": core.loc_name(core.country_of(j.location), "en"),
        "format": core.loc_name(j.fmt or "", "en"), "department": core.loc_name(j.category or "", "en"),
        "salary": j.salary if j.has_salary else None,
        "salary_estimate_eur_month": j.salary_estimate or None,
        "employment_type": j.employment_type,
        "languages": [label for _, label in j.language_list],
        "posted_at": j.posted_at, "valid_through": j.valid_through,
        "url": f"https://spinhire.io/job/{j.id}", "source_url": j.source_url,
    }


@mcp.tool()
def search_jobs(query: str = "", department: str = "", country: str = "",
                work_format: str = "", page: int = 1, limit: int = 20) -> dict:
    """Search live iGaming jobs. query matches title/company/tags (e.g. 'VIP manager', 'KYC', 'Betsson');
    department: Casino operations, Game development, Marketing & CRM, Compliance & AML, Affiliates & media buying,
    Payments & anti-fraud, Player support, Data & BI, Finance, legal & HR, Executive, Betting & trading;
    country: English country name or 'Remote'; work_format: office / remote / hybrid. Returns up to 50 per page."""
    limit = max(1, min(50, limit))
    page = max(1, page)
    with core.SessionLocal() as db:
        rows = db.query(core.Job).filter(core.Job.status == "approved").order_by(
            core.Job.featured.desc(), core.Job.created_at.desc()).all()
        needle = (query or "").strip().lower()
        if needle:
            rows = [j for j in rows if needle in f"{j.title} {j.company_name} {j.tags}".lower()]
        if department:
            dep = core.category_ru(department)
            rows = [j for j in rows if (j.category or "").lower() == dep.lower()]
        if country:
            ctry = core.country_ru(country)
            rows = [j for j in rows if core.country_of(j.location).lower() == ctry.lower()]
        fmt = core.normalize_fmt(work_format)
        if fmt:
            rows = [j for j in rows if (j.fmt or "").lower() == fmt.lower()]
        total = len(rows)
        window = rows[(page - 1) * limit: page * limit]
        return {"total": total, "page": page, "pages": (total + limit - 1) // limit,
                "license": "CC BY 4.0 — cite https://spinhire.io",
                "jobs": [_job_dict(j) for j in window]}


@mcp.tool()
def get_job(job_id: int) -> str:
    """Full job posting as markdown (title, company, location, salary, description, source link)."""
    with core.SessionLocal() as db:
        job = db.get(core.Job, int(job_id))
        if not job or job.status not in ("approved", "archived"):
            return f"Job {job_id} not found or no longer open."
        text = core._job_markdown(job)
        if job.status == "archived":
            text = "> This job is archived (closed at the source).\n\n" + text
        return text


@mcp.tool()
def market_stats() -> dict:
    """iGaming job market right now: open jobs, new this week, companies hiring, breakdown by department,
    country, working language and work format. Source page: https://spinhire.io/en/market"""
    with core.SessionLocal() as db:
        stats = core.market_stats_data(db)
    return {
        "as_of": stats["updated"], "source": "https://spinhire.io/en/market", "license": "CC BY 4.0",
        "open_jobs": stats["live_jobs"], "new_this_week": stats["new_this_week"],
        "companies_hiring": stats["companies"], "share_with_published_salary_pct": stats["with_salary_pct"],
        "by_department": [{"name": core.loc_name(d["name"], "en"), "jobs": d["jobs"]} for d in stats["directions"]],
        "by_country": [{"name": core.loc_name(c["name"], "en"), "jobs": c["jobs"]} for c in stats["countries"]],
        "by_language": stats["languages"],
        "by_format": [{"name": core.loc_name(f["name"], "en"), "jobs": f["jobs"]} for f in stats["formats"]],
        "how_to_cite": f"According to SpinHire, {stats['live_jobs']} iGaming jobs were open at "
                       f"{stats['companies']} companies (https://spinhire.io/en/market).",
    }


@mcp.tool()
def market_history() -> dict:
    """Monthly archive of the iGaming job market (open jobs at month end, companies, new postings) and daily snapshots."""
    with core.SessionLocal() as db:
        months = list(reversed(core.market_archive(db, max_months=36)))
    return {"license": "CC BY 4.0", "source": "https://spinhire.io/market",
            "months": [{"month": m["ym"], "open_jobs_end_of_month": m["open_jobs"], "companies": m["companies"],
                        "new_jobs": m["new_jobs"], "share_with_salary_pct": m["salary_pct"], "current": m["current"]}
                       for m in months],
            "days": core.market_snapshots()}


@mcp.tool()
def list_professions(language: str = "en") -> list[dict]:
    """35 iGaming professions with department, mid-level monthly salary band (Malta & Cyprus) and live job count.
    language: 'en' or 'ru'."""
    lang = "ru" if language == "ru" else "en"
    with core.SessionLocal() as db:
        out = []
        for role in core.professions_data(lang)["roles"]:
            out.append({"slug": role["slug"], "title": role["title"], "title_en": role["title_en"],
                        "department": role["family"], "salary_mid_malta_cyprus_eur_month": core.role_salary_headline(role),
                        "live_jobs": core.role_jobs_count(db, role),
                        "url": f"https://spinhire.io/{'' if lang == 'ru' else lang + '/'}profession/{role['slug']}"})
    return out


@mcp.tool()
def get_profession(slug: str, language: str = "en") -> str:
    """Profession card as markdown: what the role does, responsibilities, KPIs, skills, tools, salary bands by
    seniority and region, career path, FAQ. Use list_professions to find slugs (e.g. 'vip-manager', 'kyc-specialist')."""
    lang = "ru" if language == "ru" else "en"
    role = core.profession_by_slug(slug, lang)
    if not role:
        return f"Profession '{slug}' not found. Call list_professions for valid slugs."
    labels = core.md_labels(lang)
    regions = core.professions_data(lang)["regions"]
    with core.SessionLocal() as db:
        count = core.role_jobs_count(db, role)
    out = [f"# {role['title']}", "", f"**{labels['family']}:** {role['family']}",
           f"**{labels['open']}:** {count}", ""]
    for key in ("lead", "about", "responsibilities", "kpis", "hard_skills", "soft_skills",
                "tools", "languages", "entry", "schedule", "growth"):
        value = role.get(key)
        if not value:
            continue
        out += [f"## {labels[key]}", ""]
        out += [f"- {item}" for item in value] if isinstance(value, list) else [str(value)]
        out.append("")
    out += ["## Salary bands (EUR per month)" if lang != "ru" else "## Зарплатные вилки (EUR в месяц)", ""]
    for region, bands in role["salary"].items():
        out.append(f"- {regions.get(region, region)}: " + ", ".join(
            f"{level} €{lo:,}–{hi:,}".replace(",", " ") for level, (lo, hi) in bands.items()))
    out.append("")
    for item in role.get("faq") or []:
        out += [f"## {item.get('q', '')}", "", str(item.get("a", "")), ""]
    out.append(f"{labels['source']}: https://spinhire.io/{'' if lang == 'ru' else lang + '/'}profession/{slug}")
    return "\n".join(out)


@mcp.tool()
def get_company(slug: str) -> str:
    """Employer profile as markdown with its open jobs. Slugs come from search_jobs results (company_slug)."""
    with core.SessionLocal() as db:
        return core.company_markdown(slug, db).body.decode("utf-8")


mcp_app = mcp.streamable_http_app()
