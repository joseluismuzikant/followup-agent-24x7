"""Products on the platform. Each product's API knows its own and only ever sees its own
tenants, profiles and jobs; core keeps the rules, the product supplies its onboarding steps,
business types and setup checklist (`ProductDefinition`)."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from .errors import InvalidBusinessTypeError


class Product(StrEnum):
    INMO24X7 = "inmo24x7"
    CUENTAS_CLARAS = "cuentas_claras"


# The first product: core adapters default to it so code written before there were two
# products keeps working. Every other product passes its own key explicitly.
FIRST_PRODUCT = Product.INMO24X7


@dataclass(frozen=True, slots=True)
class ProductDefinition:
    """What a product decides about its businesses; core applies the rules."""

    product: Product
    # Ordered wizard steps; reaching the last one finishes the onboarding.
    onboarding_steps: Sequence[str]
    # Where a new sign-up lands: the steps before it are completed by the sign-up itself.
    first_step: str
    business_types: Sequence[str]
    # The panel's setup checklist, in order: (item key, fact key). The facts themselves are
    # computed per request by the product's fact providers (GetSetupChecklist).
    checklist: Sequence[tuple[str, str]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if len(self.onboarding_steps) < 2:
            raise ValueError("An onboarding needs at least two steps.")
        if self.first_step not in self.onboarding_steps:
            raise ValueError(f"Unknown first step '{self.first_step}'.")

    @property
    def last_step(self) -> str:
        return self.onboarding_steps[-1]

    def parse_business_type(self, value: str) -> str:
        if value not in self.business_types:
            raise InvalidBusinessTypeError(f"Unknown business type '{value}'.")
        return value
