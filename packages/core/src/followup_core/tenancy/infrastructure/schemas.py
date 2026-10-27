from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime
    status: str
    trial_ends_at: datetime


class TenantPageRead(BaseModel):
    items: list[TenantRead]
    page: int
    limit: int
    total: int
    total_pages: int


class ErrorResponse(BaseModel):
    code: str
