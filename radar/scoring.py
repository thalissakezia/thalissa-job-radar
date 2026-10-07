from __future__ import annotations

from dataclasses import dataclass

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
    "desenvolvedor senior",
    "devops senior",
    "network engineer",
    "administrador de redes",
    "infraestrutura",
)

TITLE_WEIGHTS = {
    "power bi": 7,
    "analista de dados": 7,
    "assistente de dados": 7,
    "business intelligence": 6,
    "data analyst": 6,
    "dados": 4,
    "relatorio": 3,
    "indicador": 3,
    "qualidade de dados": 5,
    "cadastro": 4,
    "backoffice": 4,
    "administrativo": 3,
    "operacoes": 3,
    "atendimento": 4,
    "customer service": 4,
    "suporte": 4,
    "support": 4,
    "implantacao": 4,
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

    score = 0

    for term, weight in TITLE_WEIGHTS.items():
        if normalize(term) in title:
            score += weight
            reasons.append(f"título combina com {term}")
            break

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

    # Soft penalties: these do not auto-reject because descriptions are often noisy.
    advanced_language = (
        "ingles avancado",
        "english advanced",
        "advanced english",
        "espanhol avancado",
        "spanish advanced",
    )
    if any(term in body for term in advanced_language):
        score -= 4
        reasons.append("idioma avançado aparece na descrição")

    if "active directory" in body or "servidores linux" in body or "redes tcp/ip" in body:
        score -= 4
        reasons.append("suporte/infra avançado aparece na descrição")

    score = max(score, 0)

    if score >= 10:
        label = "PRIORIDADE"
    elif score >= 6:
        label = "SECUNDÁRIA"
    else:
        label = "REVISAR"

    return Match(score, False, label, reasons)
