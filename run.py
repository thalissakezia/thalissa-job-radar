from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from radar.scoring import evaluate
from radar.sources import collect_all
from radar.store import HistoryStore

ROOT = Path(__file__).resolve().parent


def esc(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def format_salary(job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "não informada"

    currency = job.salary_currency or ""
    symbol = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£"}.get(
        currency, currency
    )

    def money(value):
        if value is None:
            return None
        if currency == "BRL":
            return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{value:,.0f}"

    low = money(job.salary_min)
    high = money(job.salary_max)
    if low and high:
        value = f"{symbol} {low}–{high}".strip()
    else:
        value = f"{symbol} {low or high}".strip()

    periods = {
        "monthly": "mês",
        "yearly": "ano",
        "hourly": "hora",
        "weekly": "semana",
        "daily": "dia",
    }
    if job.salary_period:
        value += f"/{periods.get(job.salary_period, job.salary_period)}"
    return value


def application_text(job) -> str:
    if job.easy_apply:
        return "Easy Apply"
    if job.direct_url:
        return "Link direto"
    return "Normal"


def application_link(job) -> str:
    target = job.direct_url or job.url
    return f"[Aplicar]({target})"


def main() -> None:
    config = json.loads((ROOT / "config/search.json").read_text(encoding="utf-8"))
    jobs, diagnostics = collect_all(
        config["search_terms"],
        config.get("freehire_posted_within_days", 2),
        config.get("gupy_posted_within_days", 3),
        config.get("jobspy_queries"),
        config.get("jobspy_hours_old", 30),
        config.get("jobspy_results_wanted", 20),
    )

    store = HistoryStore(
        ROOT / "data/radar_runtime.db",
        ROOT / "data/seen_jobs.json",
    )

    new_matches: list[tuple] = []
    new_total = 0
    rejected_new = 0

    try:
        for job in jobs:
            match = evaluate(job, config["allowed_rj_locations"])
            is_new = store.record(job, match.score, match.label)
            if not is_new:
                continue

            new_total += 1
            if match.rejected:
                rejected_new += 1
                continue

            if match.score >= config.get("min_score", 3):
                new_matches.append((job, match))

        store.export_json()
    finally:
        store.close()

    new_matches.sort(key=lambda pair: pair[1].score, reverse=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Thalissa Job Radar — última execução",
        "",
        f"Executado em **{now}**.",
        "",
        f"- Vagas únicas coletadas nesta execução: **{len(jobs)}**",
        f"- Vagas nunca vistas antes: **{new_total}**",
        f"- Novas vagas descartadas por regra objetiva: **{rejected_new}**",
        f"- Novas vagas para revisar/candidatar: **{len(new_matches)}**",
        "",
        "## Novidades",
        "",
    ]

    if new_matches:
        lines.extend(
            [
                "| Prioridade | Pontos | Empresa | Vaga | Data | Local | Salário | Candidatura | Contato | Fonte | Por quê |",
                "|---|---:|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for job, match in new_matches:
            title = esc(job.title)
            job_link = f"[{title}]({job.url})"
            apply = f"{application_text(job)} · {application_link(job)}"
            lines.append(
                "| "
                + " | ".join(
                    [
                        esc(match.label),
                        str(match.score),
                        esc(job.company),
                        job_link,
                        esc(job.posted_at or "não informada"),
                        esc(job.location or "não informada"),
                        esc(format_salary(job)),
                        apply,
                        esc(job.contact_emails or "—"),
                        esc(job.source),
                        esc("; ".join(match.reasons)),
                    ]
                )
                + " |"
            )
    else:
        lines.append("Nenhuma vaga nova atingiu a pontuação mínima nesta execução.")

    lines.extend(["", "## Saúde das fontes", ""])
    for diag in diagnostics:
        stats = diag.get("stats", {})
        lines.append(
            f"- **{diag['source']}**: {stats.get('rows', 0)} resultados brutos; "
            f"{stats.get('requests_ok', 0)} requisições OK; "
            f"{stats.get('requests_failed', 0)} falhas."
        )
        if diag.get("errors"):
            lines.append(
                "  - Primeiras falhas: "
                + " / ".join(esc(err) for err in diag["errors"][:3])
            )

    lines.extend(
        [
            "",
            "> A coleta é automática e o histórico evita repetir vagas. "
            "A comparação completa com o currículo ainda será adicionada.",
            "",
        ]
    )

    report_path = ROOT / "reports/latest.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
