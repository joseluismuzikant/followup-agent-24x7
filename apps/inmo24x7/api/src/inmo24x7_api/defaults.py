"""inmo24x7 product defaults for new tenants.

These live in the product, not in core: another product would start from a different
agent name, tone, and question list.
"""

from followup_core.tenancy.application.defaults import SetupDefaults
from followup_core.tenancy.domain.agent_config import (
    AfterHoursMode,
    AgentConfig,
    QualificationQuestion,
    QuestionKind,
    Tone,
)
from followup_core.tenancy.domain.business_settings import (
    DEFAULT_TIMEZONE,
    TEAM_HOURS_WEEKDAYS_9_18,
)


def build_setup_defaults() -> SetupDefaults:
    return SetupDefaults(
        agent_config=AgentConfig(
            agent_name="Sofía",
            tone=Tone.WARM,
            after_hours_mode=AfterHoursMode.KEEP_ANSWERING_AND_PROPOSE_VISIT,
            qualification_questions=(
                QualificationQuestion(
                    key="operation",
                    label="Si busca comprar o alquilar",
                    kind=QuestionKind.CHOICE,
                    options=("compra", "alquiler"),
                ),
                QualificationQuestion(
                    key="zone",
                    label="Zona o barrio",
                    kind=QuestionKind.TEXT,
                ),
                QualificationQuestion(
                    key="budget",
                    label="Presupuesto",
                    kind=QuestionKind.MONEY,
                ),
                QualificationQuestion(
                    key="rooms",
                    label="Cantidad de ambientes",
                    kind=QuestionKind.NUMBER,
                ),
                # Asked only when the chosen property needs them (leads/conditions.py),
                # never up front; each can be turned off in Agente → Preguntas.
                QualificationQuestion(
                    key="garantia",
                    label="Qué garantía tiene para alquilar",
                    kind=QuestionKind.CHOICE,
                    options=("propietaria", "caucion", "recibo_de_sueldo", "ninguna", "otra"),
                ),
                QualificationQuestion(
                    key="plazo_meses",
                    label="Por cuántos meses quiere alquilar",
                    kind=QuestionKind.NUMBER,
                ),
                QualificationQuestion(
                    key="necesita_credito",
                    label="Si necesita crédito hipotecario",
                    kind=QuestionKind.BOOLEAN,
                ),
            ),
        ),
        team_hours=TEAM_HOURS_WEEKDAYS_9_18,
        timezone=DEFAULT_TIMEZONE,
    )
