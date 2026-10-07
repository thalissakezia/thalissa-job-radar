from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Iterable
from urllib.parse import quote

import requests

from radar.models import Job, normalize_currency

USER_AGENT = "thalissa-job-radar/0.3 (+github.com/thalissakezia/thalissa-job-radar)"
TIMEOUT = 25

_GUPY_SEARCH = "https://portal.gupy.io/job-search/term="
_GUPY_NEXT_DATA = re.compile(
    r"<script[^>]*__NEXT_DATA__[^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def _text(value) -> str:
    return "" if value is None else str(value).strip()


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
        return float(value)
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
    """
    Gupy removed the old public JSON search endpoint in Oct/2026.
    The current public search page still embeds the initial result list in
    Next.js __NEXT_DATA__, so we read that server-rendered payload directly.
    No login, cookie, browser automation or candidate account is required.
    """
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
                    if not _gupy_is_old(item, cutoff):
                        page_all_old = False

                    description = _text(
                        _first(item, "description", "jobDescription")
                    )
                    workplace = _text(
                        _first(item, "workplaceType", "workplace", "type")
                    )
                    if item.get("isRemoteWork") is True and not workplace:
                        workplace = "remote"

                    company = _text(
                        _first(item, "careerPageName", "companyName")
                    )
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

                # Result pages are newest-first. Once a whole page is older than
                # the collection window, later pages are not useful for the radar.
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


def collect_all(
    search_terms: list[str],
    freehire_days: int,
    gupy_days: int = 3,
) -> tuple[list[Job], list[dict]]:
    jobs: list[Job] = []
    diagnostics: list[dict] = []

    for collector in (
        lambda: fetch_freehire(search_terms, freehire_days),
        lambda: fetch_gupy(search_terms, gupy_days),
    ):
        collected, diag = collector()
        jobs.extend(collected)
        diagnostics.append(diag)

    unique: dict[str, Job] = {}
    for job in jobs:
        if job.title and job.company and job.url:
            unique.setdefault(job.fingerprint, job)

    return list(unique.values()), diagnostics
