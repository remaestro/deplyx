from datetime import datetime

from pydantic import BaseModel


class SiteCreate(BaseModel):
    name: str
    slug: str | None = None
    location: str | None = None
    organization_id: int | None = None


class SiteUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    location: str | None = None


class SiteRead(BaseModel):
    id: int
    organization_id: int
    name: str
    slug: str
    location: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrganizationCreate(BaseModel):
    name: str
    slug: str | None = None


class OrganizationRead(BaseModel):
    id: int
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
    sites: list[SiteRead] = []

    model_config = {"from_attributes": True}
