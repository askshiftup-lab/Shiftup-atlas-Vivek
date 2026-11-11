"""Pytest configuration and reusable fixtures for Atlas quality testing.

Defines client fixtures (mock vs real service mode), deterministic synthetic user
factories, test database isolation, and pre-authenticated test contexts.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any, Callable

import httpx
import pytest

from tests.mocks import InMemoryState, MockAuthClient, MockProfileClient


@pytest.fixture(autouse=True)
def reset_test_state() -> Generator[None, None, None]:
    """Ensure in-memory mock database state is completely cleared before and after each test.

    Yield-based cleanup guarantees that test executions are strictly independent
    and leave no leftover records.
    """
    InMemoryState.reset()
    yield
    InMemoryState.reset()


@pytest.fixture
def test_db_state() -> type[InMemoryState]:
    """Provide access to the in-memory database state for side-effect assertions."""
    return InMemoryState


@pytest.fixture(scope="session")
def stable_test_config() -> dict[str, Any]:
    """Provide stable, deterministic test configuration without production credentials."""
    return {
        "auth_base_url": os.getenv("ATLAS_AUTH_URL", "").strip(),
        "profile_base_url": os.getenv("ATLAS_PROFILE_URL", "").strip(),
        "default_password": "PolicyPass123!",  # PROVISIONAL: valid mock policy password
        "default_verification_code": "123456",  # PROVISIONAL: valid mock code
        "timeout_seconds": 5.0,
    }


@pytest.fixture
def service_mode(stable_test_config: dict[str, Any]) -> str:
    """Determine whether tests run against mock clients or real services.

    Returns:
        "real" if both ATLAS_AUTH_URL and ATLAS_PROFILE_URL are set, else "mock".
    """
    if os.getenv("TEST_SERVICE_MODE") == "real":
        return "real"
    return "mock"


@pytest.fixture
def auth_client(service_mode: str, stable_test_config: dict[str, Any]):
    """Return MockAuthClient by default, or an httpx.Client if ATLAS_AUTH_URL is set."""
    if service_mode == "real":
        client = httpx.Client(
            base_url=stable_test_config["auth_base_url"],
            timeout=stable_test_config["timeout_seconds"],
        )
        yield client
        client.close()
    else:
        yield MockAuthClient()


@pytest.fixture
def profile_client(service_mode: str, stable_test_config: dict[str, Any]):
    """Return MockProfileClient by default, or an httpx.Client if ATLAS_PROFILE_URL is set."""
    if service_mode == "real":
        client = httpx.Client(
            base_url=stable_test_config["profile_base_url"],
            timeout=stable_test_config["timeout_seconds"],
        )
        yield client
        client.close()
    else:
        yield MockProfileClient()


@pytest.fixture
def synthetic_user() -> Callable[..., dict[str, str]]:
    """Deterministic factory fixture generating synthetic test user identities."""

    def _factory(
        index: int = 1,
        email: str | None = None,
        password: str | None = None,
        username: str | None = None,
        first_name: str | None = None,
        phone: str | None = None,
    ) -> dict[str, str]:
        uname = username or f"synthetic_user_{index}"
        fname = first_name or f"User{index}"
        return {
            "email": email or f"user{index}@example.com",
            "password": password or "PolicyPass123!",
            "username": uname,
            "first_name": fname,
            "phone": phone or "+91 98765 43210",
        }

    return _factory


@pytest.fixture
def logged_in_user(
    auth_client: Any, synthetic_user: Callable[..., dict[str, str]]
) -> dict[str, Any]:
    """Helper fixture chaining register -> verify -> login.

    Returns the user data dict along with authentication headers ready for requests.
    """
    user = synthetic_user(index=10)
    # 1. Register
    reg_resp = auth_client.request("POST", "/auth/register", json=user)  # PROVISIONAL
    assert reg_resp.status_code == 201, f"Failed registration: {reg_resp.text}"

    # 2. Verify challenge
    verify_resp = auth_client.request(
        "POST",
        "/auth/verify",  # PROVISIONAL
        json={"email": user["email"], "code": "123456"},  # PROVISIONAL
    )
    assert verify_resp.status_code == 200, f"Failed verification: {verify_resp.text}"

    # 3. Login
    login_resp = auth_client.request(
        "POST",
        "/auth/login",  # PROVISIONAL
        json={"email": user["email"], "password": user["password"]},
    )
    assert login_resp.status_code == 200, f"Failed login: {login_resp.text}"
    token = login_resp.json()["access_token"]

    return {
        "user": user,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def two_users(auth_client: Any, synthetic_user: Callable[..., dict[str, str]]) -> dict[str, Any]:
    """Fixture generating two distinct logged-in users for cross-user authorization tests."""
    users_data = {}
    for idx, key in [(21, "user_a"), (22, "user_b")]:
        u = synthetic_user(index=idx)
        auth_client.request("POST", "/auth/register", json=u)  # PROVISIONAL
        auth_client.request(
            "POST", "/auth/verify", json={"email": u["email"], "code": "123456"}  # PROVISIONAL
        )
        l_resp = auth_client.request(
            "POST", "/auth/login", json={"email": u["email"], "password": u["password"]}
        )
        token = l_resp.json()["access_token"]
        users_data[key] = {
            "user": u,
            "token": token,
            "user_id": l_resp.json()["user_id"],
            "headers": {"Authorization": f"Bearer {token}"},
        }

    return users_data
