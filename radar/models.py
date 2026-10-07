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

    @property
    def key(self) -> str:
        return f"{self.source}:{self.external_id or self.url}"

    @property
    def fingerprint(self) -> str:
        # Cross-source duplicate key. Location is kept so the same role in
        # different cities is not collapsed accidentally.
        basis = "|".join(
            [normalize(self.company), normalize(self.title), normalize(self.location)]
        )
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()
