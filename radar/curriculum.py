from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from radar.models import Job, normalize


@dataclass(slots=True)
class CurriculumFit:
    profile_id: str
    profile_name: str
    curriculum_file: str
    percent: int
    confidence: str
    recommendation: str
    matches: list[str]
    gaps: list[str]


GAP_RULES = (
    ("inglês avançado", ("ingles avancado", "advanced english", "fluent english", "ingles fluente"), 12),
    ("espanhol avançado", ("espanhol avancado", "advanced spanish", "fluent spanish"), 10),
    ("Tableau", ("tableau",), 5),
    ("Looker", ("looker", "looker studio"), 4),
    ("AWS", (" aws ", "amazon web services"), 5),
    ("Azure", (" azure ", "microsoft azure"), 5),
    ("Airflow", ("airflow",), 5),
    ("Spark", ("spark", "pyspark"), 5),
    ("dbt", (" dbt ",), 5),
    ("Salesforce", ("salesforce",), 5),
    ("SAP", (" sap ",), 5),
    ("Active Directory", ("active directory",), 8),
    ("Windows Server", ("windows server",), 7),
    ("Linux avançado", ("redhat linux", "servidores linux", "linux server"), 6),
    ("redes/TCP-IP", ("tcp/ip", "redes de computadores", "networking"), 7),
)


def load_profiles(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles") or []
    if not profiles:
        raise ValueError("curriculum profile configuration is empty")
    return profiles


def _phrase_present(text: str, phrase: str) -> bool:
    phrase = normalize(phrase)
    if not phrase:
        return False
    if len(phrase) <= 3:
        return re.search(rf"\b{re.escape(phrase)}\b", text) is not None
    return phrase in text


def _role_strength(title: str, profile: dict[str, Any]) -> tuple[int, list[str]]:
    hits: list[tuple[int, str]] = []
    for item in profile.get("role_terms", []):
        term = item["term"]
        if _phrase_present(title, term):
            hits.append((int(item.get("weight", 1)), term))
    if not hits:
        return 0, []
    hits.sort(reverse=True)
    best_weight = hits[0][0]
    # 10 => 45 points, 8 => 36, 6 => 27.
    points = min(45, round(best_weight * 4.5))
    return points, [term for _, term in hits[:3]]


def _skill_points(body: str, profile: dict[str, Any]) -> tuple[int, list[str]]:
    weighted_hits: list[tuple[int, str]] = []
    for item in profile.get("skills", []):
        term = item["term"]
        if _phrase_present(body, term):
            weighted_hits.append((int(item.get("weight", 1)), term))
    weighted_hits.sort(reverse=True)
    total_weight = sum(weight for weight, _ in weighted_hits)
    points = min(35, round(total_weight * 3.2))
    return points, [term for _, term in weighted_hits[:6]]


def _transferable_points(body: str, profile: dict[str, Any]) -> tuple[int, list[str]]:
    hits = [
        term
        for term in profile.get("transferable_terms", [])
        if _phrase_present(body, term)
    ]
    return min(10, len(hits) * 2), hits[:4]


def _education_points(body: str, profile: dict[str, Any]) -> tuple[int, list[str]]:
    if not profile.get("has_higher_education"):
        return 0, []
    higher_ed_terms = (
        "ensino superior",
        "graduacao",
        "graduado",
        "superior completo",
        "curso superior",
        "tecnologo",
        "formacao superior",
    )
    if any(term in body for term in higher_ed_terms):
        return 8, ["formação superior compatível"]
    # Education is still useful, but do not award the full requirement score
    # when the vacancy never states a degree requirement.
    return 3, ["formação superior disponível"]


def _entry_level_bonus(title: str, body: str) -> tuple[int, list[str]]:
    terms = ("junior", "jr", "júnior", "estagio", "estágio", "trainee", "assistente", "auxiliar")
    if any(_phrase_present(title, term) for term in terms):
        return 5, ["nível de entrada/júnior"]
    if "sem experiencia" in body or "primeira oportunidade" in body:
        return 5, ["aceita pouca/nenhuma experiência"]
    return 0, []


def _gap_penalties(body: str, profile: dict[str, Any]) -> tuple[int, list[str]]:
    owned = {
        normalize(item["term"])
        for item in profile.get("skills", [])
    }
    penalty = 0
    gaps: list[str] = []

    for label, variants, points in GAP_RULES:
        if not any(normalize(variant) in f" {body} " for variant in variants):
            continue
        # If the profile explicitly owns the same technology, it is not a gap.
        if any(normalize(variant).strip() in owned for variant in variants):
            continue
        penalty += points
        gaps.append(label)

    # Detect an explicit minimum-years requirement. It is intentionally marked as
    # a potential gap rather than an automatic rejection.
    years = [
        int(value)
        for value in re.findall(
            r"(?:minimo|minima|pelo menos|ao menos|experiencia de|experiencia minima de)\s*(\d+)\s*anos?",
            body,
        )
    ]
    if years:
        required = max(years)
        direct = int(profile.get("direct_experience_years", 0))
        if required > direct:
            penalty += min(15, (required - direct) * 4)
            gaps.append(f"pede {required} ano(s) de experiência direta")

    return penalty, gaps[:5]


def evaluate_curriculum_fit(
    job: Job,
    profiles: list[dict[str, Any]],
) -> CurriculumFit:
    title = normalize(job.title)
    description = normalize(job.description)
    body = normalize(f"{job.title} {job.description}")

    # Pick the curriculum family from the job title first. A support vacancy
    # should stay in the Support profile even when it has many missing technical
    # requirements; otherwise a low-scoring unrelated profile could "win".
    role_data = []
    for profile in profiles:
        role_points, role_hits = _role_strength(title, profile)
        role_data.append((profile, role_points, role_hits))

    max_role = max((points for _, points, _ in role_data), default=0)
    candidates = (
        [item for item in role_data if item[1] == max_role]
        if max_role > 0
        else role_data
    )

    best: CurriculumFit | None = None

    for profile, raw_role_points, role_hits in candidates:
        role_points = raw_role_points or 12
        skill_points, skill_hits = _skill_points(body, profile)
        transferable_points, transferable_hits = _transferable_points(body, profile)
        education_points, education_hits = _education_points(body, profile)
        entry_points, entry_hits = _entry_level_bonus(title, body)
        penalty, gaps = _gap_penalties(body, profile)

        description_len = len(description)
        if description_len < 80:
            confidence = "baixa"
            percent = min(72, role_points + entry_points + 20)
        elif description_len < 350:
            confidence = "média"
            percent = (
                role_points
                + skill_points
                + transferable_points
                + education_points
                + entry_points
                - penalty
            )
        else:
            confidence = "alta"
            percent = (
                role_points
                + skill_points
                + transferable_points
                + education_points
                + entry_points
                - penalty
            )

        percent = max(0, min(100, round(percent)))

        matches: list[str] = []
        if role_hits:
            matches.append("cargo: " + ", ".join(role_hits))
        if skill_hits:
            matches.append("competências: " + ", ".join(skill_hits))
        if transferable_hits:
            matches.append("experiência transferível: " + ", ".join(transferable_hits))
        matches.extend(education_hits)
        matches.extend(entry_hits)

        if confidence == "baixa":
            recommendation = "REVISAR DESCRIÇÃO"
        elif percent >= 78 and len(gaps) <= 1:
            recommendation = "VALE CANDIDATAR"
        elif percent >= 62:
            recommendation = "PODE VALER"
        else:
            recommendation = "REVISAR"

        fit = CurriculumFit(
            profile_id=profile["id"],
            profile_name=profile["name"],
            curriculum_file=profile["curriculum_file"],
            percent=percent,
            confidence=confidence,
            recommendation=recommendation,
            matches=matches[:5],
            gaps=gaps,
        )

        if best is None or fit.percent > best.percent:
            best = fit

    assert best is not None
    return best
