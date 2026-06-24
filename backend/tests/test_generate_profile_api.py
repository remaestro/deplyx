"""Tests pour l'endpoint POST /connectors/generate-profile.

Attention : utilise des ``output_path`` temporaires pour ne pas
écraser les vrais profils dans ``profiles/``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.schemas.connector import ProfileGenerateRequest, ProfileGenerateResult


@pytest.fixture
def tmp_profile() -> str:
    """Chemin temporaire pour le profil généré."""
    return str(Path(tempfile.mkdtemp()) / "test-profile.yml")


@pytest.mark.asyncio
async def test_generate_profile_manual_mode(
    client: AsyncClient, tmp_profile: str
) -> None:
    """Mode manuel : vendor + os_name doit retourner un profil.

    Pour un vendeur/OS connu (cisco/ios), le profil existant est réutilisé
    (match-first) sans appel LLM. Le chemin retourné est le profil canonique.
    """
    await client.post(
        "/api/v1/auth/register",
        json={"email": "gen-admin@deplyx.io", "password": "Admin123!", "role": "admin"},
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "gen-admin@deplyx.io", "password": "Admin123!"},
    )
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/v1/connectors/generate-profile",
        json={"vendor": "cisco", "os_name": "ios", "output_path": tmp_profile},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["profile"]["vendor"] == "cisco"
    assert data["profile"]["os"] == "ios"
    assert len(data["yaml_str"]) > 0
    # match-first: le profil canonique existant est retourné, pas le tmp_profile
    assert data["path"].endswith("cisco-ios.yml")


@pytest.mark.asyncio
async def test_generate_profile_missing_vendor(client: AsyncClient) -> None:
    """Sans vendor ni host, doit retourner une erreur."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "gen-fail@deplyx.io", "password": "Admin123!", "role": "admin"},
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "gen-fail@deplyx.io", "password": "Admin123!"},
    )
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/v1/connectors/generate-profile",
        json={},
        headers=headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_generate_profile_requires_admin(client: AsyncClient) -> None:
    """Seul un admin peut générer des profils."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "gen-net@deplyx.io", "password": "Net12345!", "role": "network"},
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "gen-net@deplyx.io", "password": "Net12345!"},
    )
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/v1/connectors/generate-profile",
        json={"vendor": "cisco", "os_name": "ios", "output_path": "/tmp/test-fail.yml"},
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_generate_profile_fortinet(
    client: AsyncClient, tmp_profile: str
) -> None:
    """Test avec Fortinet pour valider un autre constructeur."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "gen-ftnt@deplyx.io", "password": "Admin123!", "role": "admin"},
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "gen-ftnt@deplyx.io", "password": "Admin123!"},
    )
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/v1/connectors/generate-profile",
        json={"vendor": "fortinet", "os_name": "fortios", "output_path": tmp_profile},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["profile"]["vendor"] == "fortinet"
    transports = data["profile"]["transports"]
    device_types = [t["device_type"] for t in transports if t.get("device_type")]
    assert len(device_types) > 0


@pytest.mark.asyncio
async def test_generate_profile_schema(
    client: AsyncClient, tmp_profile: str
) -> None:
    """Vérifie que la réponse respecte le schéma ProfileGenerateResult."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "gen-schema@deplyx.io", "password": "Admin123!", "role": "admin"},
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "gen-schema@deplyx.io", "password": "Admin123!"},
    )
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/v1/connectors/generate-profile",
        json={
            "vendor": "test-vendor",
            "os_name": "test-os",
            "output_path": tmp_profile,
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    model = ProfileGenerateResult(**data)
    assert model.status == "ok"
    assert model.profile["vendor"] == "test-vendor"
    assert model.path == tmp_profile
