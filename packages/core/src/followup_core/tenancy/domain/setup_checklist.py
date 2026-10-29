from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class SetupFacts:
    """Everything the product knows about a tenant's setup. Later days own most facts."""

    account_created: bool
    agent_configured: bool
    agent_tested: bool
    whatsapp_connected: bool
    own_properties: bool
    meta_business_verified: bool


class ChecklistItemKey(StrEnum):
    ACCOUNT = "account"
    AGENT = "agent"
    WHATSAPP = "whatsapp"
    PROPERTIES = "properties"
    META = "meta"


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    key: ChecklistItemKey
    done: bool


@dataclass(frozen=True, slots=True)
class SetupChecklist:
    """The five items shown on the panel, plus every fact for the backoffice."""

    items: tuple[ChecklistItem, ...]
    facts: SetupFacts

    @classmethod
    def from_facts(cls, facts: SetupFacts) -> "SetupChecklist":
        return cls(
            items=(
                ChecklistItem(ChecklistItemKey.ACCOUNT, facts.account_created),
                ChecklistItem(ChecklistItemKey.AGENT, facts.agent_configured),
                ChecklistItem(ChecklistItemKey.WHATSAPP, facts.whatsapp_connected),
                ChecklistItem(ChecklistItemKey.PROPERTIES, facts.own_properties),
                ChecklistItem(ChecklistItemKey.META, facts.meta_business_verified),
            ),
            facts=facts,
        )

    @property
    def ready_count(self) -> int:
        return sum(item.done for item in self.items)

    @property
    def total(self) -> int:
        return len(self.items)
