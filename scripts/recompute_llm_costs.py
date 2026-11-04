"""Recompute the cost of recorded LLM calls after fixing a price in llm_prices.toml.

    uv run --all-packages python scripts/recompute_llm_costs.py --from 2026-11-01
    uv run --all-packages python scripts/recompute_llm_costs.py --from 2026-11-01 --apply

A dry run by default: it prints, per month (UTC), the rows whose cost would change and the
totals before and after. --apply writes the new costs. In production, run it in the API
image: `docker compose run --rm api python scripts/recompute_llm_costs.py --from ...`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING

from _cli import ROOT, load_env_file

if TYPE_CHECKING:
    from followup_core.conversation.domain.usage import PriceBook
    from sqlalchemy.orm import Session


def main(
    argv: list[str] | None = None,
    sessions: Callable[[], Session] | None = None,
    prices: PriceBook | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Recalcula el costo de las llamadas al LLM.")
    parser.add_argument(
        "--from",
        dest="since",
        required=True,
        type=date.fromisoformat,
        help="primer día (UTC), AAAA-MM-DD",
    )
    parser.add_argument("--apply", action="store_true", help="guardar los costos nuevos")
    args = parser.parse_args(argv)
    load_env_file(ROOT / ".env")

    from followup_core.conversation.infrastructure.usage import recompute_costs
    from inmo24x7_api.billing.infrastructure.prices import load_prices

    if sessions is None:
        from inmo24x7_api.database import SessionLocal

        sessions = SessionLocal
    with sessions() as session:
        months = recompute_costs(session, prices or load_prices(), args.since, apply=args.apply)
        if args.apply:
            session.commit()

    if not months:
        print(f"No hay llamadas desde el {args.since}.")
        return 0
    for month in months:
        print(
            f"{month.month}: {month.rows_changed} filas cambian · "
            f"USD {month.before_usd:.4f} → {month.after_usd:.4f}"
            + (f" · {month.unpriced} sin precio" if month.unpriced else "")
        )
    changed = sum(month.rows_changed for month in months)
    if args.apply:
        print(f"Listo: {changed} filas actualizadas.")
    else:
        print(f"Simulación: {changed} filas cambiarían. Repetí con --apply para guardarlas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
