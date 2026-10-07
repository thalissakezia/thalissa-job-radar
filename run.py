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

    if job.salary_period:
        value += f"/{job.salary_period}"
    return value


def main() -> None:
    config = json.loads((ROOT / "config/search.json").read_text(encoding="utf-8"))
    jobs, diagnostics = collect_all(
        config["search_terms"],
        config.get("freehire_posted_within_days", 2),
        config.get("gupy_posted_within_days", 3),
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
                "| Prioridade | Pontos | Empresa | Vaga | Data da fonte | Local | Salário | Fonte | Por quê |",
                "|---|---:|---|---|---|---|---|---|---|",
            ]
        )
        for job, match in new_matches:
            title = esc(job.title)
            link = f"[{title}]({job.url})"
            lines.append(
                "| "
                + " | ".join(
                    [
                        esc(match.label),
                        str(match.score),
                        esc(job.company),
                        link,
                        esc(job.posted_at or "não informada"),
                        esc(job.location or "não informada"),
                        esc(format_salary(job)),
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
            "> Nesta primeira versão, a classificação é determinística. "
            "A IA ainda não decide aderência e nenhuma candidatura é enviada automaticamente.",
            "",
        ]
    )

    report_path = ROOT / "reports/latest.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
