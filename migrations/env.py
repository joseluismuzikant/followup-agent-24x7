from logging.config import fileConfig

from alembic import context
from cuentas_claras_api.clients.infrastructure import models as clients_models  # noqa: F401
from cuentas_claras_api.invoices.infrastructure import models as invoices_models  # noqa: F401
from cuentas_claras_api.payments.infrastructure import models as payments_models  # noqa: F401
from cuentas_claras_api.reminders.infrastructure import models as reminders_models  # noqa: F401
from followup_core.conversation.infrastructure import models as conversation_models  # noqa: F401
from followup_core.identity.infrastructure import models as identity_models  # noqa: F401
from followup_core.infrastructure.db import Base
from followup_core.messaging.infrastructure import models as messaging_models  # noqa: F401
from followup_core.scheduling.infrastructure import models as scheduling_models  # noqa: F401
from followup_core.tenancy.infrastructure import models as tenancy_models  # noqa: F401
from followup_platform.settings import ProductSpec, load_settings
from inmo24x7_api.leads.infrastructure import models as leads_models  # noqa: F401
from inmo24x7_api.properties.infrastructure import models as properties_models  # noqa: F401
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

configured_url = config.get_main_option("sqlalchemy.url")
if not configured_url:
    config.set_main_option(
        "sqlalchemy.url",
        # One database for every product: any product's settings name it (DATABASE_URL).
        load_settings(ProductSpec()).database_url.replace("%", "%%"),
    )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
