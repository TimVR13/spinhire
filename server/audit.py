"""Аудит качества опубликованных вакансий.

Правило площадки: у каждой живой вакансии данные должны быть достоверными и
однородными. Модуль приводит к норме то, что источники отдают криво:

* дубли одной роли (один источник отдал позицию несколько раз, или её же
  прислал агрегатор) — оставляем карточку с самым полным описанием;
* мусор в заголовках: немецкие гендер-суффиксы (m/w/d), польские [K/M],
  эмодзи, хвосты «- Malta», двойные пробелы;
* зарплаты-пустышки: «€40 000 – €40 000» (равные границы) и нули;
* локации с улицами и запятыми-хвостами: «Київ, вулиця …, 1., » → «Киев, Украина».

Запуск вручную:  python -m server.audit
Из краулера:     audit_jobs(db, Job) после обогащения.
"""
import re
from datetime import datetime

# (m/w/d), (m/f/x), [K/M], (к/м) — служебные гендер-пометки вакансий DE/PL
_GENDER_RE = re.compile(r"\s*[\(\[]\s*[mwfdxкмжk]\s*[/|]\s*[mwfdxкмжk]\s*(?:[/|]\s*[mwfdxкмжk]\s*)?[\)\]]", re.I)
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_TITLE_TAIL_RE = re.compile(r"\s*[-–—]\s*(?:malta|cyprus|remote|hybrid|onsite|poland|kyiv|київ)\s*$", re.I)
_STREET_RE = re.compile(r",?\s*(?:вулиця|улица|вул\.|ул\.|street|str\.|просп\w*|бульвар)[^,]*", re.I)


def clean_title(title: str) -> str:
    out = _GENDER_RE.sub("", title or "")
    out = _EMOJI_RE.sub("", out)
    out = _TITLE_TAIL_RE.sub("", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" -–—·|")
    return out


def clean_location(location: str) -> str:
    out = _STREET_RE.sub("", location or "")
    out = re.sub(r"\s*,\s*(?:\d+\.?)\s*", ", ", out)
    out = re.sub(r"[\s,\.]+$", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def clean_salary(salary: str) -> str:
    """«€40 000 – €40 000» → «€40 000»; нулевые вилки → «по запросу»."""
    s = (salary or "").strip()
    if not s:
        return "по запросу"
    numbers = re.findall(r"[\d][\d  ']*", s)
    if len(numbers) >= 2:
        left, right = numbers[0].replace(" ", "").replace(" ", ""), numbers[1].replace(" ", "").replace(" ", "")
        if left == right:
            # оставляем одно значение вместе с валютой/суффиксом
            head = s.split("–")[0].split("-")[0].strip()
            return head or s
    if re.fullmatch(r"[^\d]*0[^\d]*", s):
        return "по запросу"
    return s


def _dup_key(job):
    def norm(value):
        return re.sub(r"[^a-zа-я0-9]+", "", (value or "").lower())
    return (norm(clean_title(job.title)), norm(job.company_name)[:12],
            norm(job.location)[:16])


def audit_jobs(db, Job, log=print) -> dict:
    jobs = db.query(Job).filter(Job.status == "approved").all()
    fixed_titles = fixed_locations = fixed_salaries = merged = 0

    for job in jobs:
        new_title = clean_title(job.title)
        if new_title and new_title != job.title:
            job.title = new_title
            fixed_titles += 1
        new_location = clean_location(job.location)
        if new_location != (job.location or ""):
            job.location = new_location
            fixed_locations += 1
        new_salary = clean_salary(job.salary)
        if new_salary != (job.salary or ""):
            job.salary = new_salary
            fixed_salaries += 1

    # дубли: у одной роли остаётся карточка с самым полным описанием
    groups = {}
    for job in jobs:
        groups.setdefault(_dup_key(job), []).append(job)
    today = datetime.utcnow().date().isoformat()
    for key, group in groups.items():
        if len(group) < 2 or not key[0]:
            continue
        group.sort(key=lambda j: (len(j.description or ""), j.id), reverse=True)
        for loser in group[1:]:
            loser.status = "archived"
            loser.closed_at = today
            merged += 1

    db.commit()
    summary = {"titles": fixed_titles, "locations": fixed_locations,
               "salaries": fixed_salaries, "duplicates_archived": merged}
    log(f"[audit] {summary}")
    return summary


if __name__ == "__main__":
    import sys
    sys.path.insert(0, __file__.rsplit("/server/", 1)[0])
    from server.app import SessionLocal, Job
    audit_jobs(SessionLocal(), Job)
