"""Live integration smoke tests for Auth and Profile services.

CRITICAL INTEGRATION RULE:
These tests ONLY execute when real service URLs are provided via the environment
variables ATLAS_AUTH_URL and ATLAS_PROFILE_URL. If either is missing, tests MUST
be SKIPPED with an explicit explanation. They never run against mocks.
"""

from __future__ import annotations

import os

import httpx
import pytest

AUTH_URL = os.getenv("ATLAS_AUTH_URL", "").strip()
PROFILE_URL = os.getenv("ATLAS_PROFILE_URL", "").strip()
HAS_LIVE_SERVICES = bool(AUTH_URL and PROFILE_URL)
SKIP_REASON = (
    "Live integration tests skipped: ATLAS_AUTH_URL and/or ATLAS_PROFILE_URL "
    "are not configured. Real service deployments required."
)


@pytest.mark.integration
@pytest.mark.skipif(not HAS_LIVE_SERVICES, reason=SKIP_REASON)
def test_live_auth_service_health_smoke():
    """Verify live Auth service is reachable over HTTP and returns a healthy status."""
    with httpx.Client(base_url=AUTH_URL, timeout=5.0) as client:
        # PROVISIONAL: health check path for auth service
        response = client.get("/health")
        assert response.status_code in (200, 204), (
            f"Auth service at {AUTH_URL} unhealthy: {response.status_code}"
        )


@pytest.mark.integration
@pytest.mark.skipif(not HAS_LIVE_SERVICES, reason=SKIP_REASON)
def test_live_profile_service_health_smoke():
    """Verify live Profile service is reachable over HTTP and returns a healthy status."""
    with httpx.Client(base_url=PROFILE_URL, timeout=5.0) as client:
        # PROVISIONAL: health check path for profile service
        response = client.get("/health")
        assert response.status_code in (200, 204), (
            f"Profile service at {PROFILE_URL} unhealthy: {response.status_code}"
        )


@pytest.mark.integration
@pytest.mark.skipif(not HAS_LIVE_SERVICES, reason=SKIP_REASON)
def test_live_end_to_end_user_lifecycle_smoke(synthetic_user):
    """End-to-end integration test against live services: register, verify, login, read profile."""
    user = synthetic_user(index=999)

    with httpx.Client(base_url=AUTH_URL, timeout=5.0) as auth_cli:
        # 1. Register user
        reg_resp = auth_cli.post("/auth/register", json=user)  # PROVISIONAL
        assert reg_resp.status_code in (200, 201)

        # 2. Verify code
        verify_resp = auth_cli.post(
            "/auth/verify",  # PROVISIONAL
            json={"email": user["email"], "code": "123456"},  # PROVISIONAL
        )
        assert verify_resp.status_code == 200

        # 3. Login
        login_resp = auth_cli.post(
            "/auth/login",  # PROVISIONAL
            json={"email": user["email"], "password": user["password"]},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

    # 4. Access profile service using token
    with httpx.Client(base_url=PROFILE_URL, timeout=5.0) as prof_cli:
        prof_resp = prof_cli.get(
            "/profiles/me",  # PROVISIONAL
            headers={"Authorization": f"Bearer {token}"},
        )
        assert prof_resp.status_code == 200
