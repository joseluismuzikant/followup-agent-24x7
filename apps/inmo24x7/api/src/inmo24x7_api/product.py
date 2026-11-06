"""inmo24x7 as a product of the platform: its onboarding steps, business types and setup
checklist (core applies the rules; these are inmo24x7's values, unchanged since Day 2)."""

from enum import StrEnum

from followup_core.tenancy.domain.product import Product, ProductDefinition

PRODUCT = Product.INMO24X7


class OnboardingStep(StrEnum):
    BUSINESS = "business"
    AGENT = "agent"
    TRY = "try"
    WHATSAPP = "whatsapp"
    DONE = "done"


STEP_ORDER: tuple[OnboardingStep, ...] = tuple(OnboardingStep)


class BusinessType(StrEnum):
    AGENCY = "inmobiliaria"
    NETWORK = "red_franquicia"
    BROKER = "corredor"
    DEVELOPER = "desarrolladora"


# Every fact the panel and the backoffice read, in the order of the API's `facts` object.
FACTS = (
    "account_created",
    "agent_configured",
    "agent_tested",
    "whatsapp_connected",
    "own_properties",
    "meta_business_verified",
)

DEFINITION = ProductDefinition(
    product=PRODUCT,
    onboarding_steps=STEP_ORDER,
    # Sign-up completes "business" and lands on "agent".
    first_step=OnboardingStep.AGENT,
    business_types=tuple(BusinessType),
    checklist=(
        ("account", "account_created"),
        ("agent", "agent_configured"),
        ("whatsapp", "whatsapp_connected"),
        ("properties", "own_properties"),
        ("meta", "meta_business_verified"),
    ),
)
