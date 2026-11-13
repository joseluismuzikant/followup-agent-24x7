"""Argentine national holidays: the `holidays` package (fixed ones, Easter-based ones and
the movable ones moved to Monday by law 27.399), corrected by holidays_ar.toml (extra
non-sending dates such as each year's "días no laborables con fines turísticos", and dates
to remove). The file can be fixed without a code change."""

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import holidays

OVERRIDES = Path(__file__).resolve().parents[1] / "holidays_ar.toml"


@dataclass(frozen=True, slots=True)
class Overrides:
    extra: frozenset[date]
    removed: frozenset[date]


def _dates(values: Iterable[object], name: str) -> frozenset[date]:
    parsed: set[date] = set()
    for value in values:
        if isinstance(value, date):
            parsed.add(value)
        elif isinstance(value, str):
            parsed.add(date.fromisoformat(value))
        else:
            raise ValueError(f"holidays_ar.toml: {name} must hold dates, got {value!r}.")
    return frozenset(parsed)


def load_overrides(path: Path = OVERRIDES) -> Overrides:
    if not path.exists():
        return Overrides(frozenset(), frozenset())
    data = tomllib.loads(path.read_text("utf-8"))
    return Overrides(
        _dates(data.get("extra", []), "extra"), _dates(data.get("removed", []), "removed")
    )


def package_holidays(years: Iterable[int]) -> dict[date, str]:
    """What the package computes, with Spanish names."""
    found = holidays.country_holidays("AR", years=sorted(set(years)), language="es")
    return dict(sorted(found.items()))


@lru_cache(maxsize=16)
def _year(year: int, path: Path) -> frozenset[date]:
    overrides = load_overrides(path)
    days = set(package_holidays([year])) | {day for day in overrides.extra if day.year == year}
    return frozenset(days - overrides.removed)


def argentine_holidays(years: Iterable[int], path: Path = OVERRIDES) -> frozenset[date]:
    days: set[date] = set()
    for year in set(years):
        days |= _year(year, path)
    return frozenset(days)
