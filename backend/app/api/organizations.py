from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import Role, require_role
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationRead,
    SiteCreate,
    SiteRead,
    SiteUpdate,
)
from app.services import org_service

router = APIRouter(tags=["organizations"])


# ── Organizations ──────────────────────────────────────────────────────


@router.get("/organizations", response_model=list[OrganizationRead])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    orgs = await org_service.list_organizations(db)
    if current_user.role != Role.ADMIN and current_user.organization_id is not None:
        orgs = [o for o in orgs if o.id == current_user.organization_id]
    return orgs


@router.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    return await org_service.create_organization(db, body.model_dump())


# ── Sites ────────────────────────────────────────────────────────────


@router.get("/sites", response_model=list[SiteRead])
async def list_sites(
    organization_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = organization_id
    if current_user.role != Role.ADMIN:
        org_id = current_user.organization_id
    return await org_service.list_sites(db, organization_id=org_id)


@router.post("/sites", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
async def create_site(
    body: SiteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    org_id = body.organization_id or current_user.organization_id
    if org_id is None:
        raise HTTPException(status_code=400, detail="organization_id is required")
    return await org_service.create_site(db, org_id, body.model_dump(exclude={"organization_id"}))


@router.put("/sites/{site_id}", response_model=SiteRead)
async def update_site(
    site_id: int,
    body: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    site = await org_service.update_site(db, site_id, body.model_dump(exclude_unset=True))
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.delete("/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    deleted = await org_service.delete_site(db, site_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Site not found")
