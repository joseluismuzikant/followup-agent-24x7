"""Cuentas Claras as a product of the platform: its onboarding steps, business types and
setup checklist."""

from enum import StrEnum

from followup_core.tenancy.domain.product import Product, ProductDefinition

PRODUCT = Product.CUENTAS_CLARAS


class OnboardingStep(StrEnum):
    BUSINESS = "business"  # Tu negocio
    INVOICES = "invoices"  # Tus facturas
    REMINDERS = "reminders"  # Recordatorios (a preview until Day 9)
    CONNECT = "connect"  # Conectar WhatsApp y Mercado Pago (Day 9)
    DONE = "done"  # Listo


class BusinessType(StrEnum):
    MAINTENANCE = "mantenimiento"  # ascensores, matafuegos, climatización
    SECURITY = "seguridad"  # seguridad y monitoreo
    IT_SUPPORT = "soporte_it"
    AGENCY = "agencia"  # agencia con abonos
    OTHER = "otro"  # otro servicio mensual


FACTS = (
    "account_created",
    "invoices_loaded",
    "whatsapp_connected",
    "mercado_pago_connected",
    "reminders_configured",
)

DEFINITION = ProductDefinition(
    product=PRODUCT,
    onboarding_steps=tuple(OnboardingStep),
    first_step=OnboardingStep.INVOICES,
    business_types=tuple(BusinessType),
    checklist=(
        ("account", "account_created"),
        ("invoices", "invoices_loaded"),
        ("whatsapp", "whatsapp_connected"),
        ("mercado_pago", "mercado_pago_connected"),
        ("reminders", "reminders_configured"),
    ),
)
