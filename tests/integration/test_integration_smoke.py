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
        response = client.get("/healthz")
        if response.status_code == 404:
            response = client.get("/health")
        assert response.status_code in (200, 204), (
            f"Auth service at {AUTH_URL} unhealthy: {response.status_code}"
        )


@pytest.mark.integration
@pytest.mark.skipif(not HAS_LIVE_SERVICES, reason=SKIP_REASON)
def test_live_profile_service_health_smoke():
    """Verify live Profile service is reachable over HTTP and returns a healthy status."""
    with httpx.Client(base_url=PROFILE_URL, timeout=5.0) as client:
        response = client.get("/healthz")
        if response.status_code == 404:
            response = client.get("/health")
        assert response.status_code in (200, 204), (
            f"Profile service at {PROFILE_URL} unhealthy: {response.status_code}"
        )


@pytest.mark.integration
@pytest.mark.skipif(not HAS_LIVE_SERVICES, reason=SKIP_REASON)
def test_live_end_to_end_user_lifecycle_smoke(synthetic_user):
    """End-to-end integration test against live services:
    Register (Task A) -> Verify OTP (Task A) -> Login (Task A) ->
    Create & Read Profile (Task B) -> Save Interests (Task B).
    """
    import uuid

    unique_suffix = uuid.uuid4().hex[:6]
    user = synthetic_user(
        index=999,
        email=f"e2e_{unique_suffix}@example.com",
        username=f"user_{unique_suffix}",
    )

    with httpx.Client(base_url=AUTH_URL, timeout=5.0) as auth_cli:
        # 1. Register user (Task A)
        reg_resp = auth_cli.post("/v1/auth/registrations", json=user)
        assert reg_resp.status_code in (200, 201, 202), f"Registration failed: {reg_resp.text}"

        # 2. Verify code (Task A)
        verify_resp = auth_cli.post(
            "/v1/auth/email-verifications/confirm",
            json={"email": user["email"], "code": "123456"},
        )
        assert verify_resp.status_code == 200, f"Verification failed: {verify_resp.text}"

        # 3. Login (Task A)
        login_resp = auth_cli.post(
            "/v1/auth/sessions",
            json={"email": user["email"], "password": user["password"]},
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json()["access_token"]

    # 4. Access profile service using token (Task B)
    with httpx.Client(base_url=PROFILE_URL, timeout=5.0) as prof_cli:
        prof_headers = {"Authorization": f"Bearer {token}"}

        # 4a. Create / initialize profile (Task B)
        patch_resp = prof_cli.patch(
            "/v1/profile",
            json={"first_name": user["first_name"], "username": user["username"]},
            headers=prof_headers,
        )
        assert patch_resp.status_code == 200, f"Profile patch failed: {patch_resp.text}"

        # 4b. Read profile (Task B)
        prof_resp = prof_cli.get("/v1/profile", headers=prof_headers)
        assert prof_resp.status_code == 200, f"Profile read failed: {prof_resp.text}"
        assert prof_resp.json()["username"] == user["username"]

        # 4c. Fetch available active interests catalogue
        cat_resp = prof_cli.get("/v1/interests", headers=prof_headers)
        assert cat_resp.status_code == 200
        available_interests = cat_resp.json().get("items", [])
        assert len(available_interests) > 0, "No active interests available in catalogue"
        selected_ids = [item["id"] for item in available_interests[:2]]

        # 4d. Save interests (Task B)
        int_resp = prof_cli.put(
            "/v1/profile/interests",
            json={"interest_ids": selected_ids},
            headers=prof_headers,
        )
        assert int_resp.status_code == 200, f"Save interests failed: {int_resp.text}"
        assert len(int_resp.json()["items"]) == len(selected_ids)
