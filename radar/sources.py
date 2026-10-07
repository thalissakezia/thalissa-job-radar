from __future__ import annotations

from collections import Counter
from typing import Iterable

import requests

from radar.models import Job

USER_AGENT = "thalissa-job-radar/0.1 (+github.com/thalissakezia/thalissa-job-radar)"
TIMEOUT = 25


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _first(data: dict, *names: str) -> str | None:
    for name in names:
        value = data.get(name)
        if value not in (None, ""):
            return _text(value)
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
        # One query catches Brazil-located jobs, the second catches remote roles
        # that explicitly target LATAM/global rather than a single country.
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
                    jobs.append(
                        Job(
                            source=f"freehire/{_text(item.get('source')) or 'catalog'}",
                            external_id=_text(external_id),
                            title=_text(item.get("title")),
                            company=_text(item.get("company")),
                            location=_text(item.get("location")),
                            url=_text(item.get("url")),
                            description=_text(item.get("description")),
                            posted_at=_first(item, "posted_at", "created_at"),
                            work_mode=_text(
                                item.get("work_mode")
                                or enrichment.get("work_mode")
                            ),
                        )
                    )
                    stats["rows"] += 1
                stats["requests_ok"] += 1
            except Exception as exc:
                errors.append(f"{term}: {type(exc).__name__}: {exc}")
                stats["requests_failed"] += 1

    return jobs, {"source": "FreeHire", "stats": dict(stats), "errors": errors[:10]}


def fetch_gupy(search_terms: Iterable[str]) -> tuple[list[Job], dict]:
    """
    Uses the portal's public employability endpoint. It is not a documented
    public API, so the adapter fails visibly if Gupy changes the contract.
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://portal.gupy.io",
            "Referer": "https://portal.gupy.io/",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        }
    )
    endpoint = "https://employability-portal.gupy.io/api/v1/jobs"
    jobs: list[Job] = []
    stats = Counter()
    errors: list[str] = []

    for term in search_terms:
        try:
            response = session.get(
                endpoint,
                params={"jobName": term},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                raise ValueError("Gupy returned an unexpected data shape")

            for item in items:
                location_parts = [
                    _first(item, "city"),
                    _first(item, "state"),
                    _first(item, "country"),
                ]
                location = ", ".join(part for part in location_parts if part)
                external_id = _first(item, "id", "jobId", "jobUrl") or ""
                jobs.append(
                    Job(
                        source="gupy",
                        external_id=_text(external_id),
                        title=_text(_first(item, "name", "title")),
                        company=_text(_first(item, "companyName", "company")),
                        location=location,
                        url=_text(_first(item, "jobUrl", "url")),
                        description=_text(
                            _first(item, "description", "jobDescription")
                        ),
                        posted_at=_first(
                            item,
                            "publicationDate",
                            "publishedDate",
                            "publicDate",
                            "createdAt",
                            "created_at",
                        ),
                        work_mode=_text(
                            _first(item, "workplaceType", "workplace", "type")
                        ),
                    )
                )
                stats["rows"] += 1
            stats["requests_ok"] += 1
        except Exception as exc:
            errors.append(f"{term}: {type(exc).__name__}: {exc}")
            stats["requests_failed"] += 1

    return jobs, {"source": "Gupy", "stats": dict(stats), "errors": errors[:10]}


def collect_all(
    search_terms: list[str],
    freehire_days: int,
) -> tuple[list[Job], list[dict]]:
    jobs: list[Job] = []
    diagnostics: list[dict] = []

    for collector in (
        lambda: fetch_freehire(search_terms, freehire_days),
        lambda: fetch_gupy(search_terms),
    ):
        collected, diag = collector()
        jobs.extend(collected)
        diagnostics.append(diag)

    # Also collapses the same vacancy returned by several search terms.
    unique: dict[str, Job] = {}
    for job in jobs:
        if job.title and job.company and job.url:
            unique.setdefault(job.fingerprint, job)

    return list(unique.values()), diagnostics
