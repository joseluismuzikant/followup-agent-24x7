from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    key: str
    done: bool


@dataclass(frozen=True, slots=True)
class SetupChecklist:
    """The items shown on the panel (defined by the product), plus every fact for the
    backoffice."""

    items: tuple[ChecklistItem, ...]
    facts: Mapping[str, bool]

    @classmethod
    def from_facts(
        cls, items: Sequence[tuple[str, str]], facts: Mapping[str, bool]
    ) -> "SetupChecklist":
        """`items` are (item key, fact key) pairs, in display order."""
        return cls(
            items=tuple(ChecklistItem(key, facts[fact]) for key, fact in items),
            facts=MappingProxyType(dict(facts)),
        )

    @property
    def ready_count(self) -> int:
        return sum(item.done for item in self.items)

    @property
    def total(self) -> int:
        return len(self.items)
