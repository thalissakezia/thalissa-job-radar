from __future__ import annotations

import base64
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
import re
from typing import Iterable
from urllib.parse import quote, urlparse

import requests

from radar.models import Job, normalize, normalize_currency

USER_AGENT = "thalissa-job-radar/0.4 (+github.com/thalissakezia/thalissa-job-radar)"
TIMEOUT = 25

_GUPY_SEARCH = "https://portal.gupy.io/job-search/term="
_GUPY_NEXT_DATA = re.compile(
    r"<script[^>]*__NEXT_DATA__[^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in {"nan", "nat", "<na>", "none"}:
        return ""
    return text


def _first(data: dict, *names: str) -> str | None:
    for name in names:
        value = data.get(name)
        if value not in (None, ""):
            return _text(value)
    return None


def _number(value) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    raw = str(value).strip()
    raw = raw.replace("R$", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _date_text(value) -> str | None:
    if value in (None, ""):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _extract_brl_salary(description: str) -> tuple[float | None, float | None, str | None]:
    """
    Conservative parser: only treats R$ values as salary when they are near
    'salário', 'remuneração' or 'faixa salarial'. This avoids mistaking VA/VR
    benefits for salary.
    """
    if not description:
        return None, None, None

    compact = re.sub(r"\s+", " ", description)
    prefix = r"(?:sal[aá]rio|remunera[cç][aã]o|faixa\s+salarial)"
    money = r"R\$\s*([\d.]+(?:,\d{1,2})?)"
    match = re.search(
        prefix + r"[^\n]{0,60}?" + money + r"(?:\s*(?:a|até|[-–—])\s*R?\$?\s*([\d.]+(?:,\d{1,2})?))?",
        compact,
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None, None

    low = _number(match.group(1))
    high = _number(match.group(2)) if match.group(2) else None
    around = compact[max(0, match.start() - 30): match.end() + 50].lower()
    if any(word in around for word in ("/hora", "por hora", "hora trabalhada")):
        period = "hourly"
    elif any(word in around for word in ("/ano", "por ano", "anual")):
        period = "yearly"
    else:
        period = "monthly"
    return low, high, period


def fetch_freehire(
    search_terms: Iterable[str],
    posted_within_days: int = 2,
) -> tuple[list[Job], dict]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    endpoint = "https://freehire.me/api/v1/agent/jobs/search"
    jobs: list[Job] = []
    stats = Counter()
    errors: list[str] = []

    for term in search_terms:
        searches = [
            {"countries": "BR"},
            {"work_mode": "remote", "regions": "global,latam"},
        ]
        for extra in searches:
            params = {
                "q": f'"{term}"',
                "q_fields": "title,description",
                "posted_within_days": posted_within_days,
                "sort": "posted_at",
                "order": "desc",
                "description_format": "text",
                "limit": 100,
                **extra,
            }
            try:
                response = session.get(endpoint, params=params, timeout=TIMEOUT)
                response.raise_for_status()
                payload = response.json()
                ignored = (payload.get("meta") or {}).get("ignored_params") or []
                if ignored:
                    errors.append(f"{term}: filtros ignorados pela API: {ignored}")

                for item in payload.get("data", []):
                    enrichment = item.get("enrichment") or {}
                    external_id = (
                        _first(item, "public_slug", "external_id")
                        or _text(item.get("url"))
                    )
                    description = _text(item.get("description"))
                    currency = normalize_currency(
                        enrichment.get("salary_currency")
                        or item.get("salary_currency"),
                        description,
                    )
                    jobs.append(
                        Job(
                            source=f"freehire/{_text(item.get('source')) or 'catalog'}",
                            external_id=_text(external_id),
                            title=_text(item.get("title")),
                            company=_text(item.get("company")),
                            location=_text(item.get("location")),
                            url=_text(item.get("url")),
                            description=description,
                            posted_at=_first(item, "posted_at", "created_at"),
                            work_mode=_text(
                                item.get("work_mode")
                                or enrichment.get("work_mode")
                            ),
                            salary_min=_number(
                                enrichment.get("salary_min")
                                or item.get("salary_min")
                            ),
                            salary_max=_number(
                                enrichment.get("salary_max")
                                or item.get("salary_max")
                            ),
                            salary_currency=currency,
                            salary_period=_text(
                                enrichment.get("salary_period")
                                or item.get("salary_period")
                            ) or None,
                        )
                    )
                    stats["rows"] += 1
                stats["requests_ok"] += 1
            except Exception as exc:
                errors.append(f"{term}: {type(exc).__name__}: {exc}")
                stats["requests_failed"] += 1

    return jobs, {"source": "FreeHire", "stats": dict(stats), "errors": errors[:10]}


def _gupy_extract(html: str) -> tuple[dict, list[dict]]:
    match = _GUPY_NEXT_DATA.search(html)
    if not match:
        raise ValueError("Gupy search page has no __NEXT_DATA__")
    payload = json.loads(match.group(1))
    page_props = ((payload.get("props") or {}).get("pageProps") or {})
    initial = page_props.get("initialJobList")
    if not isinstance(initial, dict):
        raise ValueError("Gupy initialJobList not found")
    data = initial.get("data") or []
    if not isinstance(data, list):
        raise ValueError("Gupy initialJobList.data is not a list")
    return initial.get("pagination") or {}, data


def _gupy_search_url(term: str, page: int) -> str:
    base = f"{_GUPY_SEARCH}{quote(term, safe='')}"
    return base if page <= 1 else f"{base}?page={page}"


def _gupy_is_old(item: dict, cutoff: datetime) -> bool:
    raw = _first(item, "publishedDate", "publicationDate", "createdAt", "created_at")
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt < cutoff
    except ValueError:
        return False


def fetch_gupy(
    search_terms: Iterable[str],
    posted_within_days: int = 3,
) -> tuple[list[Job], dict]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        }
    )

    jobs: list[Job] = []
    stats = Counter()
    errors: list[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=posted_within_days)
    max_pages = 5

    for term in search_terms:
        for page in range(1, max_pages + 1):
            url = _gupy_search_url(term, page)
            try:
                response = session.get(url, timeout=TIMEOUT)
                response.raise_for_status()
                pagination, items = _gupy_extract(response.text)
                stats["requests_ok"] += 1

                expected_offset = (page - 1) * int(pagination.get("limit") or 12)
                declared_offset = pagination.get("offset")
                if declared_offset is not None and int(declared_offset) != expected_offset:
                    errors.append(
                        f"{term}: paginação inesperada na página {page} "
                        f"(offset {declared_offset}, esperado {expected_offset})"
                    )
                    break

                if not items:
                    break

                page_all_old = True
                for item in items:
                    is_old = _gupy_is_old(item, cutoff)
                    if not is_old:
                        page_all_old = False
                    if is_old:
                        continue

                    description = _text(_first(item, "description", "jobDescription"))
                    workplace = _text(
                        _first(item, "workplaceType", "workplace", "type")
                    )
                    if item.get("isRemoteWork") is True and not workplace:
                        workplace = "remoto"
                    elif workplace.lower() == "remote":
                        workplace = "remoto"

                    company = _text(_first(item, "careerPageName", "companyName"))
                    if not company and isinstance(item.get("company"), dict):
                        company = _text(_first(item["company"], "name"))

                    location_parts = [
                        _first(item, "city"),
                        _first(item, "state"),
                        _first(item, "country"),
                    ]
                    location = ", ".join(part for part in location_parts if part)
                    external_id = _first(item, "id", "jobId", "jobUrl") or ""
                    currency = normalize_currency(
                        _first(item, "salaryCurrency", "currency"),
                        description,
                    )

                    job = Job(
                        source="gupy",
                        external_id=_text(external_id),
                        title=_text(_first(item, "name", "title")),
                        company=company,
                        location=location,
                        url=_text(_first(item, "jobUrl", "url")),
                        description=description,
                        posted_at=_first(
                            item,
                            "publishedDate",
                            "publicationDate",
                            "createdAt",
                            "created_at",
                        ),
                        work_mode=workplace,
                        salary_min=_number(_first(item, "salaryMin", "minSalary")),
                        salary_max=_number(_first(item, "salaryMax", "maxSalary")),
                        salary_currency=currency,
                        salary_period=_text(
                            _first(item, "salaryPeriod", "payPeriod")
                        ) or None,
                    )
                    if job.title and job.company and job.url:
                        jobs.append(job)
                        stats["rows"] += 1

                if page_all_old:
                    break

                total = pagination.get("total")
                limit = int(pagination.get("limit") or 12)
                if total and page * limit >= int(total):
                    break

            except Exception as exc:
                errors.append(f"{term}: {type(exc).__name__}: {exc}")
                stats["requests_failed"] += 1
                break

    return jobs, {"source": "Gupy", "stats": dict(stats), "errors": errors[:10]}


def _jobspy_row_to_job(row: dict, easy_apply_requested: bool = False) -> Job | None:
    title = _text(row.get("title"))
    company = _text(row.get("company"))
    url = _text(row.get("job_url"))
    if not title or not company or not url:
        return None

    description = _text(row.get("description"))
    salary_min = _number(row.get("min_amount"))
    salary_max = _number(row.get("max_amount"))
    salary_period = _text(row.get("interval")) or None
    currency = normalize_currency(_text(row.get("currency")), description)

    if salary_min is None and salary_max is None:
        brl_min, brl_max, brl_period = _extract_brl_salary(description)
        if brl_min is not None or brl_max is not None:
            salary_min, salary_max = brl_min, brl_max
            salary_period = brl_period
            currency = "BRL"

    is_remote = row.get("is_remote") is True
    work_mode = "remoto" if is_remote else ""

    emails = _text(row.get("emails")) or None
    direct_url = _text(row.get("job_url_direct")) or None
    source = f"jobspy/{_text(row.get('site')) or 'unknown'}"
    external_id = _text(row.get("id")) or url

    return Job(
        source=source,
        external_id=external_id,
        title=title,
        company=company,
        location=_text(row.get("location")),
        url=url,
        description=description,
        posted_at=_date_text(row.get("date_posted")),
        work_mode=work_mode,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency,
        salary_period=salary_period,
        direct_url=direct_url,
        easy_apply=easy_apply_requested,
        job_level=_text(row.get("job_level")) or None,
        contact_emails=emails,
        listing_type=_text(row.get("listing_type")) or None,
    )


def fetch_jobspy(
    search_queries: Iterable[str],
    hours_old: int = 30,
    results_wanted: int = 20,
) -> tuple[list[Job], dict]:
    """
    LinkedIn + Indeed via JobSpy. No account login or cookie is used.

    LinkedIn currently ignores JobSpy's is_remote flag, so we run two location
    sweeps (Brazil + Rio de Janeiro) and let our own classifier keep only remote
    roles or allowed RJ/Baixada cities. Easy Apply is queried first so a duplicate
    keeps the easy-apply marker during deduplication.
    """
    jobs: list[Job] = []
    stats = Counter()
    errors: list[str] = []

    try:
        from jobspy import scrape_jobs
    except Exception as exc:
        return [], {
            "source": "JobSpy",
            "stats": {"requests_failed": 1},
            "errors": [f"import: {type(exc).__name__}: {exc}"],
        }

    for term in search_queries:
        # LinkedIn: Easy Apply first, then the wider result set.
        for location in ("Brazil", "Rio de Janeiro, Brazil"):
            for easy_apply in (True, False):
                try:
                    frame = scrape_jobs(
                        site_name="linkedin",
                        search_term=term,
                        location=location,
                        distance=50,
                        easy_apply=easy_apply,
                        results_wanted=results_wanted,
                        hours_old=hours_old,
                        country_indeed="Brazil",
                        fetch_description=False,
                        description_format="plain",
                        verbose=0,
                        user_agent=USER_AGENT,
                    )
                    stats["requests_ok"] += 1
                    for record in frame.to_dict(orient="records"):
                        job = _jobspy_row_to_job(record, easy_apply_requested=easy_apply)
                        if job:
                            jobs.append(job)
                            stats["rows"] += 1
                except Exception as exc:
                    errors.append(
                        f"linkedin/{location}/{term}/easy={easy_apply}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    stats["requests_failed"] += 1

        # Indeed supports the remote flag and Brazilian country selector.
        for location, is_remote in (
            ("Rio de Janeiro, RJ", False),
            ("Brazil", True),
        ):
            try:
                frame = scrape_jobs(
                    site_name="indeed",
                    search_term=term,
                    location=location,
                    distance=50,
                    is_remote=is_remote,
                    results_wanted=results_wanted,
                    hours_old=hours_old,
                    country_indeed="Brazil",
                    fetch_description=False,
                    description_format="plain",
                    verbose=0,
                    user_agent=USER_AGENT,
                )
                stats["requests_ok"] += 1
                for record in frame.to_dict(orient="records"):
                    job = _jobspy_row_to_job(record)
                    if job:
                        jobs.append(job)
                        stats["rows"] += 1
            except Exception as exc:
                errors.append(
                    f"indeed/{location}/{term}/remote={is_remote}: "
                    f"{type(exc).__name__}: {exc}"
                )
                stats["requests_failed"] += 1

    return jobs, {"source": "JobSpy", "stats": dict(stats), "errors": errors[:12]}


def _gupy_job_id(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"https?://[^/]*gupy\.io/job/([^/?#]+)", url, re.IGNORECASE)
    if not match:
        return None
    token = match.group(1)
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        job_id = payload.get("jobId") or payload.get("jobID") or payload.get("id")
        return str(job_id) if job_id else None
    except Exception:
        return None


def _canonical_identity(job: Job) -> str:
    # Prefer the underlying ATS vacancy ID. This merges the same Gupy vacancy
    # when it is also surfaced by Indeed/JobSpy.
    for candidate in (job.direct_url, job.url):
        gupy_id = _gupy_job_id(candidate)
        if gupy_id:
            return f"gupy:{gupy_id}"

    if job.direct_url:
        parsed = urlparse(job.direct_url)
        host = parsed.netloc.lower().removeprefix("www.")
        if host and not any(domain in host for domain in ("indeed.", "linkedin.")):
            return f"direct:{host}{parsed.path.rstrip('/')}"

    city = normalize(job.location.split(",")[0]) if job.location else ""
    return "|".join(
        [
            "fallback",
            normalize(job.company),
            normalize(job.title),
            city,
        ]
    )


def collect_all(
    search_terms: list[str],
    freehire_days: int,
    gupy_days: int = 3,
    jobspy_queries: list[str] | None = None,
    jobspy_hours_old: int = 30,
    jobspy_results_wanted: int = 20,
) -> tuple[list[Job], list[dict]]:
    jobs: list[Job] = []
    diagnostics: list[dict] = []

    collectors = [
        lambda: fetch_freehire(search_terms, freehire_days),
        lambda: fetch_gupy(search_terms, gupy_days),
    ]
    if jobspy_queries:
        collectors.append(
            lambda: fetch_jobspy(
                jobspy_queries,
                hours_old=jobspy_hours_old,
                results_wanted=jobspy_results_wanted,
            )
        )

    for collector in collectors:
        collected, diag = collector()
        jobs.extend(collected)
        diagnostics.append(diag)

    unique: dict[str, Job] = {}
    for job in jobs:
        if not (job.title and job.company and job.url):
            continue
        identity = _canonical_identity(job)
        existing = unique.get(identity)
        if existing is None:
            unique[identity] = job
            continue

        # Preserve the most useful application metadata when the same vacancy is
        # seen in multiple searches/sources.
        if job.easy_apply and not existing.easy_apply:
            existing.easy_apply = True
        if not existing.direct_url and job.direct_url:
            existing.direct_url = job.direct_url
        if not existing.contact_emails and job.contact_emails:
            existing.contact_emails = job.contact_emails
        if existing.salary_min is None and job.salary_min is not None:
            existing.salary_min = job.salary_min
            existing.salary_max = job.salary_max
            existing.salary_currency = job.salary_currency
            existing.salary_period = job.salary_period
        if len(job.description or "") > len(existing.description or ""):
            existing.description = job.description
        if not existing.work_mode and job.work_mode:
            existing.work_mode = job.work_mode
        if not existing.job_level and job.job_level:
            existing.job_level = job.job_level

    return list(unique.values()), diagnostics
