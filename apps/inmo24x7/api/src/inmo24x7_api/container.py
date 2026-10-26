from typing import Annotated

from fastapi import Depends
from followup_core.tenancy.application.create_tenant import CreateTenant
from followup_core.tenancy.application.list_tenants import ListTenants
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository
from sqlalchemy.orm import Session

from .database import get_session

SessionDep = Annotated[Session, Depends(get_session)]


def create_tenant_use_case(session: SessionDep) -> CreateTenant:
    return CreateTenant(SqlAlchemyTenantRepository(session))


def list_tenants_use_case(session: SessionDep) -> ListTenants:
    return ListTenants(SqlAlchemyTenantRepository(session))
