from __future__ import annotations

from dataclasses import dataclass
import re

from radar.models import Job, normalize


@dataclass(slots=True)
class Match:
    score: int
    rejected: bool
    label: str
    reasons: list[str]


HARD_TITLE_EXCLUDES = (
    "senior",
    "sênior",
    "pleno",
    "coordenador",
    "coordenadora",
    "gerente",
    "manager",
    "diretor",
    "diretora",
    "director",
    "head ",
    "lead ",
    "líder",
)

UNRELATED_TITLE_EXCLUDES = (
    "marketing",
    "social media",
    "designer",
    "desenvolvedor",
    "developer",
    "devops",
    "network engineer",
    "administrador de redes",
    "infraestrutura",
    "professor",
    "teacher",
)

LANGUAGE_TITLE_EXCLUDES = (
    "spanish",
    "espanhol",
)

TITLE_WEIGHTS = {
    "power bi": 8,
    "analista de bi": 8,
    "assistente de bi": 8,
    "business intelligence": 7,
    "analista de dados": 8,
    "assistente de dados": 8,
    "data analyst": 7,
    "data assistant": 7,
    "analista de indicadores": 6,
    "analista de relatorios": 6,
    "qualidade de dados": 6,
    "data quality": 6,
    "cadastro": 5,
    "backoffice": 5,
    "assistente administrativo": 5,
    "auxiliar administrativo": 4,
    "analista administrativo": 4,
    "analista de operacoes": 5,
    "assistente de operacoes": 5,
    "operations analyst": 5,
    "operations assistant": 5,
    "atendimento": 5,
    "customer service": 5,
    "customer support": 5,
    "suporte": 5,
    "support": 5,
    "implantacao": 5,
    "implementation": 5,
}

SKILL_WEIGHTS = {
    "power bi": 5,
    "excel": 3,
    "dashboard": 3,
    "indicador": 2,
    "relatorio": 2,
    "sql": 1,
    "python": 1,
    "tabela dinamica": 1,
    "procv": 1,
    "procx": 1,
    "atendimento": 1,
    "suporte": 1,
    "cadastro": 1,
    "backoffice": 1,
}

REMOTE_WORDS = (
    "remote",
    "remoto",
    "home office",
    "trabalho remoto",
    "work from home",
    "wfh",
)

HYBRID_WORDS = ("hybrid", "hibrido")


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = normalize(phrase)
    if phrase == "bi":
        return re.search(r"\bbi\b", text) is not None
    return phrase in text


def evaluate(job: Job, allowed_rj_locations: list[str]) -> Match:
    title = normalize(job.title)
    body = normalize(f"{job.title} {job.description}")
    location = normalize(job.location)
    mode = normalize(job.work_mode)
    reasons: list[str] = []

    if any(normalize(term) in title for term in HARD_TITLE_EXCLUDES):
        return Match(0, True, "DESCARTADA", ["senioridade/liderança explícita no título"])

    if any(normalize(term) in title for term in UNRELATED_TITLE_EXCLUDES):
        return Match(0, True, "DESCARTADA", ["família de cargo fora do foco"])

    if any(normalize(term) in title for term in LANGUAGE_TITLE_EXCLUDES):
        return Match(0, True, "DESCARTADA", ["idioma aparece como requisito central no título"])

    score = 0
    title_match = None
    for term, weight in TITLE_WEIGHTS.items():
        if _contains_phrase(title, term):
            score += weight
            title_match = term
            reasons.append(f"título combina com {term}")
            break

    # A descrição sozinha não transforma uma vaga de outra área em vaga aderente.
    if title_match is None:
        return Match(0, True, "DESCARTADA", ["título fora das famílias de cargo configuradas"])

    skill_hits: list[str] = []
    for term, weight in SKILL_WEIGHTS.items():
        if normalize(term) in body:
            score += weight
            skill_hits.append(term)
    if skill_hits:
        reasons.append("competências: " + ", ".join(skill_hits[:4]))

    remote = any(normalize(w) in f"{mode} {location} {title}" for w in REMOTE_WORDS)
    hybrid = any(normalize(w) in f"{mode} {location} {title}" for w in HYBRID_WORDS)
    in_rj = any(normalize(place) in location for place in allowed_rj_locations)

    if remote:
        score += 3
        reasons.append("vaga remota")
    elif hybrid and in_rj:
        score += 2
        reasons.append("híbrida no RJ/Baixada")
    elif in_rj:
        score += 2
        reasons.append("localização compatível no RJ/Baixada")
    elif location:
        return Match(0, True, "DESCARTADA", ["presencial/híbrida fora da área configurada"])
    else:
        reasons.append("localização não confirmada")

    advanced_language = (
        "ingles avancado",
        "english advanced",
        "advanced english",
        "espanhol avancado",
        "spanish advanced",
        "fluente em ingles",
        "fluent english",
    )
    if any(term in body for term in advanced_language):
        score -= 4
        reasons.append("idioma avançado aparece na descrição")

    if "active directory" in body or "servidores linux" in body or "redes tcp/ip" in body:
        score -= 4
        reasons.append("suporte/infra avançado aparece na descrição")

    score = max(score, 0)

    if score >= 11:
        label = "PRIORIDADE"
    elif score >= 7:
        label = "SECUNDÁRIA"
    else:
        label = "REVISAR"

    return Match(score, False, label, reasons)
