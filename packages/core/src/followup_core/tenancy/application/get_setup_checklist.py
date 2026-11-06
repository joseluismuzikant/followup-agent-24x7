from collections.abc import Mapping, Sequence
from uuid import UUID

from ..domain.setup_checklist import SetupChecklist
from .setup_facts import FactProvider


class GetSetupChecklist:
    """Computes the product's facts for one tenant and builds its checklist from them."""

    def __init__(
        self, items: Sequence[tuple[str, str]], providers: Mapping[str, FactProvider]
    ) -> None:
        self._items = items
        self._providers = providers

    def execute(self, tenant_id: UUID) -> SetupChecklist:
        facts = {name: provider(tenant_id) for name, provider in self._providers.items()}
        return SetupChecklist.from_facts(self._items, facts)
