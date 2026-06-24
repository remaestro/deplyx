"""Multi-tenant site resolution.

The frontend selects the active site and sends its id in the ``X-Deplyx-Site``
header (or ``?site_id=`` query param). These dependencies resolve that site,
validate it belongs to the current user's organization, and expose it to
endpoints for scoping connectors, changes and topology.
"""
from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.organization import Site
from app.models.user import User
from app.services import org_service


def _parse_site_id(header_value: str | None, query_value: int | None) -> int | None:
    if query_value is not None:
        return query_value
    if header_value:
        try:
            return int(header_value)
        except ValueError:
            return None
    return None


async def resolve_optional_site(
    x_deplyx_site: str | None = Header(default=None),
    site_id: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Site | None:
    """Resolve the active site if specified, else fall back to the user's first site.

    Returns ``None`` only when the user has no organization/site at all.
    """
    requested = _parse_site_id(x_deplyx_site, site_id)
    sites = await org_service.list_sites(db, organization_id=current_user.organization_id)

    if requested is not None:
        site = next((s for s in sites if s.id == requested), None)
        if site is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Site not found or not in your organization",
            )
        return site

    return sites[0] if sites else None


async def get_current_site(
    site: Site | None = Depends(resolve_optional_site),
) -> Site:
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No site available. Create a site or select one via the X-Deplyx-Site header.",
        )
    return site
