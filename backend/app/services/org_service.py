import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.organization import Organization, Site


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "item"


# ── Organizations ──────────────────────────────────────────────────────


async def list_organizations(db: AsyncSession) -> list[Organization]:
    result = await db.execute(
        select(Organization).options(selectinload(Organization.sites)).order_by(Organization.id)
    )
    return list(result.scalars().all())


async def get_organization(db: AsyncSession, organization_id: int) -> Organization | None:
    result = await db.execute(
        select(Organization)
        .options(selectinload(Organization.sites))
        .where(Organization.id == organization_id)
    )
    return result.scalar_one_or_none()


async def create_organization(db: AsyncSession, data: dict[str, Any]) -> Organization:
    name = data["name"]
    slug = data.get("slug") or slugify(name)
    org = Organization(name=name, slug=slug)
    db.add(org)
    await db.flush()
    await db.refresh(org)
    await db.refresh(org, ["sites"])
    return org


# ── Sites ────────────────────────────────────────────────────────────


async def list_sites(db: AsyncSession, organization_id: int | None = None) -> list[Site]:
    stmt = select(Site).order_by(Site.id)
    if organization_id is not None:
        stmt = stmt.where(Site.organization_id == organization_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_site(db: AsyncSession, site_id: int) -> Site | None:
    result = await db.execute(select(Site).where(Site.id == site_id))
    return result.scalar_one_or_none()


async def create_site(db: AsyncSession, organization_id: int, data: dict[str, Any]) -> Site:
    name = data["name"]
    slug = data.get("slug") or slugify(name)
    site = Site(
        organization_id=organization_id,
        name=name,
        slug=slug,
        location=data.get("location"),
    )
    db.add(site)
    await db.flush()
    await db.refresh(site)
    return site


async def update_site(db: AsyncSession, site_id: int, data: dict[str, Any]) -> Site | None:
    site = await get_site(db, site_id)
    if site is None:
        return None
    for key, value in data.items():
        if value is not None:
            setattr(site, key, value)
    await db.flush()
    await db.refresh(site)
    return site


async def delete_site(db: AsyncSession, site_id: int) -> bool:
    site = await get_site(db, site_id)
    if site is None:
        return False
    await db.delete(site)
    await db.flush()
    return True
