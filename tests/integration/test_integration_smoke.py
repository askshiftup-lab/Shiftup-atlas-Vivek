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
    """End-to-end integration test against live services:
    Register (Task A) -> Verify OTP (Task A) -> Login (Task A) ->
    Read Profile (Task B) -> Save Interests (Task B).
    """
    user = synthetic_user(index=999)

    with httpx.Client(base_url=AUTH_URL, timeout=5.0) as auth_cli:
        # 1. Register user (Task A)
        reg_resp = auth_cli.post("/v1/auth/registrations", json=user)
        assert reg_resp.status_code in (200, 201, 202)

        # 2. Verify code (Task A)
        verify_resp = auth_cli.post(
            "/v1/auth/email-verifications/confirm",
            json={"email": user["email"], "code": "123456"},
        )
        assert verify_resp.status_code == 200

        # 3. Login (Task A)
        login_resp = auth_cli.post(
            "/v1/auth/sessions",
            json={"email": user["email"], "password": user["password"]},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

    # 4. Access profile service using token (Task B)
    with httpx.Client(base_url=PROFILE_URL, timeout=5.0) as prof_cli:
        prof_headers = {"Authorization": f"Bearer {token}"}

        # 4a. Read profile
        prof_resp = prof_cli.get("/v1/profile", headers=prof_headers)
        assert prof_resp.status_code == 200

        # 4b. Save interests
        int_resp = prof_cli.put(
            "/v1/profile/interests",
            json={"interest_ids": ["tech", "art"]},
            headers=prof_headers,
        )
        assert int_resp.status_code == 200
