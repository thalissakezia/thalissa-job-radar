from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata


def normalize(text: str | None) -> str:
    text = text or ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text.lower()).strip()
    return text


def normalize_currency(value: str | None, description: str = "") -> str | None:
    raw = (value or "").strip().upper()
    aliases = {
        "R$": "BRL",
        "BRL": "BRL",
        "REAL": "BRL",
        "REAIS": "BRL",
        "$": "USD",
        "USD": "USD",
        "US$": "USD",
        "EUR": "EUR",
        "€": "EUR",
        "GBP": "GBP",
        "£": "GBP",
    }
    if raw in aliases:
        return aliases[raw]

    body = normalize(description)
    if "r$" in description.lower() or re.search(r"\breais?\b", body):
        return "BRL"
    return raw or None


@dataclass(slots=True)
class Job:
    source: str
    external_id: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    posted_at: str | None = None
    work_mode: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    direct_url: str | None = None
    easy_apply: bool = False
    job_level: str | None = None
    contact_emails: str | None = None
    listing_type: str | None = None

    @property
    def key(self) -> str:
        return f"{self.source}:{self.external_id or self.url}"

    @property
    def fingerprint(self) -> str:
        basis = "|".join(
            [normalize(self.company), normalize(self.title), normalize(self.location)]
        )
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()
