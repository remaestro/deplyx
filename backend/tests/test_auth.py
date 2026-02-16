"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient) -> None:
    # Register
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": "test@deplyx.io", "password": "Secret123!", "role": "admin"},
    )
    assert res.status_code == 201
    register_data = res.json()
    assert "access_token" in register_data
    assert register_data["token_type"] == "bearer"

    # Login
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@deplyx.io", "password": "Secret123!"},
    )
    assert res.status_code == 200
    token_data = res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # Me
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    res = await client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200
    me = res.json()
    assert me["email"] == "test@deplyx.io"
    assert me["role"] == "Admin"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "wrong@deplyx.io", "password": "Right123!", "role": "viewer"},
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@deplyx.io", "password": "WrongPwd!"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient) -> None:
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 403
