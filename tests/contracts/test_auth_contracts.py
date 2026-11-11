"""Contract tests for Authentication and Account Service.

Validates contract specifications defined in tests/fixtures/synthetic_payloads.json.
Integrates approved Task A specifications from the Account & Auth Service.
Runs against in-memory mocks by default, or live service if ATLAS_AUTH_URL is set.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import validate

from tests.mocks import InMemoryState

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "synthetic_payloads.json"
with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
    ALL_FIXTURES = json.load(f)
AUTH_CASES = ALL_FIXTURES["auth_cases"]

# Schemas for response validation
ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["error"],
    "properties": {"error": {"type": "string"}},
}

GENERIC_MESSAGE_SCHEMA = {
    "type": "object",
    "required": ["message"],
    "properties": {"message": {"type": "string"}},
}


def _setup_preconditions(case_id: str, auth_client: Any) -> dict[str, str] | None:
    """Prepare database state required by specific test cases prior to request execution."""
    reg_payload = {
        "email": "candidate1@example.test",
        "first_name": "Candidate",
        "password": "PolicyPass123!",
        "phone": "+91 98765 43210",
    }

    if case_id == "AUTH-08-invalid-verification-code-v1":
        auth_client.request("POST", "/v1/auth/registrations", json=reg_payload)

    elif case_id == "AUTH-09-reused-verification-challenge-v1":
        auth_client.request("POST", "/v1/auth/registrations", json=reg_payload)
        auth_client.request(
            "POST",
            "/v1/auth/email-verifications/confirm",
            json={"email": "candidate1@example.test", "code": "123456"},
        )

    elif case_id == "AUTH-10-unverified-user-cannot-sign-in-v1":
        auth_client.request(
            "POST",
            "/v1/auth/registrations",
            json={
                "email": "unverified@example.test",
                "first_name": "Unverified",
                "password": "PolicyPass123!",
            },
        )

    elif case_id == "AUTH-11-invalid-credentials-v1":
        auth_client.request("POST", "/v1/auth/registrations", json=reg_payload)
        auth_client.request(
            "POST",
            "/v1/auth/email-verifications/confirm",
            json={"email": "candidate1@example.test", "code": "123456"},
        )

    elif case_id == "AUTH-13-session-revocation-v1":
        auth_client.request("POST", "/v1/auth/registrations", json=reg_payload)
        auth_client.request(
            "POST",
            "/v1/auth/email-verifications/confirm",
            json={"email": "candidate1@example.test", "code": "123456"},
        )
        login_resp = auth_client.request(
            "POST",
            "/v1/auth/sessions",
            json={"email": "candidate1@example.test", "password": "PolicyPass123!"},
        )
        token = login_resp.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}

    return None


@pytest.mark.contract
@pytest.mark.parametrize("case", AUTH_CASES, ids=[c["id"] for c in AUTH_CASES])
def test_auth_contract_cases(
    case: dict[str, Any],
    auth_client: Any,
    test_db_state: type[InMemoryState],
    service_mode: str,
):
    """Parametrized contract execution verifying status codes and response schemas."""
    print(f"\n[Contract Test] Running {case['id']} in {service_mode.upper()} mode")

    # 1. Prepare prerequisites if specified by case
    extra_headers = _setup_preconditions(case["id"], auth_client)

    # 2. Execute HTTP request via client
    method = case["method"]
    path = case["path"]
    payload = case["payload"]

    response = auth_client.request(
        method=method, path=path, json=payload, headers=extra_headers
    )

    # 3. Assert HTTP status code matches contract expectation
    assert response.status_code == case["expected_status"], (
        f"Case {case['id']} failed: expected {case['expected_status']}, "
        f"got {response.status_code}. Response: {response.text}"
    )

    # 4. Schema assertions
    if case["expected_status"] == 204:
        # 204 No Content has no body
        return

    data = response.json()
    if case["expected_status"] >= 400:
        validate(instance=data, schema=ERROR_RESPONSE_SCHEMA)
    elif case["expected_status"] == 202:
        validate(instance=data, schema=GENERIC_MESSAGE_SCHEMA)

    # 5. Side-effect assertions under mock mode
    if service_mode == "mock":
        if case["id"] in (
            "AUTH-02-missing-email-v1",
            "AUTH-03-malformed-email-v1",
            "AUTH-04-invalid-password-policy-v1",
            "AUTH-05-missing-first-name-v1",
            "AUTH-06-invalid-phone-format-v1",
        ):
            assert len(test_db_state.users) == 0, "Failed request must not create user records"
        elif case["id"] == "AUTH-01-valid-registration-v1":
            user = test_db_state.users.get("candidate1@example.test")
            assert user is not None
            assert user["account_status"] == "pending"
            assert user["phone_number"] == "+919876543210"
            assert user["phone_verified_at"] is None
            assert user["email_verified_at"] is None
        elif case["id"] == "AUTH-07-client-cannot-set-phone-verified-at":
            user = test_db_state.users.get("tamperphone@example.test")
            assert user is not None
            assert user["account_status"] == "pending"
            assert user["phone_verified_at"] is None


@pytest.mark.contract
def test_auth_invalid_registration_creates_no_partial_records(
    auth_client: Any, test_db_state: type[InMemoryState], service_mode: str
):
    """Negative test: Invalid registration requests must not create partial DB records."""
    print(f"\n[Negative Test] Running invalid registration atomicity in {service_mode} mode")

    bad_payload = {
        "email": "fresh_user@example.test",
        "first_name": "Fresh",
        "password": "123",  # violates password policy
        "phone": "+91 98765 43210",
    }
    resp = auth_client.request("POST", "/v1/auth/registrations", json=bad_payload)
    assert resp.status_code == 422

    if service_mode == "mock":
        assert "fresh_user@example.test" not in test_db_state.users
        assert "fresh_user@example.test" not in test_db_state.verification_codes
        assert "fresh_user@example.test" not in test_db_state.profiles


@pytest.mark.contract
def test_auth_client_tampering_cannot_elevate_status(
    auth_client: Any, test_db_state: type[InMemoryState], service_mode: str
):
    """Negative security test: Client cannot set phone_verified_at or account_status directly."""
    tamper_payload = {
        "email": "tamper@example.test",
        "first_name": "Tamper",
        "password": "PolicyPass123!",
        "phone": "+91 98765 43210",
        "phone_verified_at": "2026-01-01T12:00:00Z",
        "account_status": "active",
        "email_verified_at": "2026-01-01T12:00:00Z",
    }
    resp = auth_client.request("POST", "/v1/auth/registrations", json=tamper_payload)
    assert resp.status_code == 202

    if service_mode == "mock":
        user = test_db_state.users["tamper@example.test"]
        assert user["phone_verified_at"] is None
        assert user["email_verified_at"] is None
        assert user["account_status"] == "pending"


@pytest.mark.contract
def test_auth_session_revocation_lifecycle(
    auth_client: Any, service_mode: str
):
    """Contract test: Session revocation immediately terminates authentication."""
    # 1. Register & verify user
    reg = auth_client.request(
        "POST",
        "/v1/auth/registrations",
        json={
            "email": "revokeme@example.test",
            "first_name": "Revoke",
            "password": "PolicyPass123!",
        },
    )
    assert reg.status_code == 202
    auth_client.request(
        "POST",
        "/v1/auth/email-verifications/confirm",
        json={"email": "revokeme@example.test", "code": "123456"},
    )

    # 2. Login to get session
    login = auth_client.request(
        "POST",
        "/v1/auth/sessions",
        json={"email": "revokeme@example.test", "password": "PolicyPass123!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Access current session
    current = auth_client.request("GET", "/v1/auth/sessions/current", headers=headers)
    assert current.status_code == 200

    # 4. Revoke session
    revoke = auth_client.request("DELETE", "/v1/auth/sessions/current", headers=headers)
    assert revoke.status_code == 204

    # 5. Subsequent access must be rejected
    post_revoke = auth_client.request("GET", "/v1/auth/sessions/current", headers=headers)
    assert post_revoke.status_code == 401


@pytest.mark.contract
def test_auth_repeated_verification_attempts_blocked_by_rate_limit(
    auth_client: Any, service_mode: str
):
    """Negative test: Repeated wrong verification codes must trigger lockout."""
    user_payload = {
        "email": "locked_target@example.test",
        "first_name": "LockoutUser",
        "password": "PolicyPass123!",
    }
    reg_resp = auth_client.request("POST", "/v1/auth/registrations", json=user_payload)
    assert reg_resp.status_code == 202

    # Send 3 consecutive invalid verification attempts
    for attempt_num in range(1, 4):
        err_resp = auth_client.request(
            "POST",
            "/v1/auth/email-verifications/confirm",
            json={"email": user_payload["email"], "code": f"00000{attempt_num}"},
        )
        assert err_resp.status_code == 400

    # 4th attempt exceeds max attempts limit -> must return error (400)
    blocked_resp = auth_client.request(
        "POST",
        "/v1/auth/email-verifications/confirm",
        json={"email": user_payload["email"], "code": "123456"},
    )
    assert blocked_resp.status_code == 400
    validate(instance=blocked_resp.json(), schema=ERROR_RESPONSE_SCHEMA)


@pytest.mark.contract
def test_auth_database_cleanup_isolation(test_db_state: type[InMemoryState], service_mode: str):
    """Negative test: Prove test suite starts and finishes with zero leftover records."""
    if service_mode == "mock":
        assert len(test_db_state.users) == 0
        assert len(test_db_state.active_tokens) == 0
