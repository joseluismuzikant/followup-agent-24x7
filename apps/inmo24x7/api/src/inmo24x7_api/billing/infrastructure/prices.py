"""Loads llm_prices.toml into a PriceBook (see the file for the format and the rules)."""

import tomllib
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

from followup_core.conversation.domain.usage import Price, PriceBook

# Next to the package, where it is easy to find and edit.
PRICES_FILE = Path(__file__).resolve().parents[1] / "llm_prices.toml"


class PriceFileError(ValueError):
    pass


def _amount(entry: dict[str, Any], key: str, index: int) -> Decimal | None:
    raw = entry.get(key, "")
    if raw == "" or raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation as error:
        raise PriceFileError(f"price #{index}: {key} must be a number in quotes.") from error
    if value < 0:
        raise PriceFileError(f"price #{index}: {key} cannot be negative.")
    return value


def parse_prices(content: str) -> PriceBook:
    """Entries with an empty input or output price are skipped (not priced yet)."""
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise PriceFileError(f"invalid TOML: {error}") from error
    prices: list[Price] = []
    seen: set[tuple[str, date]] = set()
    for index, entry in enumerate(data.get("price", []), start=1):
        model = str(entry.get("model", "")).strip()
        effective_from = entry.get("effective_from")
        if ":" not in model:
            raise PriceFileError(f"price #{index}: model must look like 'provider:model'.")
        if not isinstance(effective_from, date):
            raise PriceFileError(f"price #{index}: effective_from must be a date (2026-11-01).")
        if (model, effective_from) in seen:
            raise PriceFileError(f"price #{index}: {model} has two prices from {effective_from}.")
        seen.add((model, effective_from))
        input_price = _amount(entry, "input_per_mtok", index)
        output_price = _amount(entry, "output_per_mtok", index)
        cached_price = _amount(entry, "cached_input_per_mtok", index)
        if input_price is None or output_price is None:
            continue
        prices.append(
            Price(
                model=model,
                effective_from=effective_from,
                input_per_mtok=input_price,
                output_per_mtok=output_price,
                cached_input_per_mtok=cached_price,
                source=str(entry.get("source", "")),
            )
        )
    return PriceBook(prices)


@lru_cache
def load_prices(path: Path = PRICES_FILE) -> PriceBook:
    return parse_prices(path.read_text(encoding="utf-8"))
