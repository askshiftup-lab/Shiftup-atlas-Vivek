"""Contract tests for Profile and Interests Service.

Validates contract specifications defined in tests/fixtures/synthetic_payloads.json.
Runs against in-memory mocks by default, or live service if ATLAS_PROFILE_URL is set.
All endpoints, response shapes, and status codes are marked as # PROVISIONAL.
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
PROFILE_CASES = ALL_FIXTURES["profile_cases"]

# Loose provisional schemas
ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["error"],  # PROVISIONAL
    "properties": {"error": {"type": "string"}},
}

PROFILE_SUCCESS_SCHEMA = {
    "type": "object",
    "required": ["user_id", "username"],  # PROVISIONAL
    "properties": {
        "user_id": {"type": "string"},
        "username": {"type": "string"},
        "interests": {"type": "array"},
    },
}

INTERESTS_SUCCESS_SCHEMA = {
    "type": "object",
    "required": ["interests"],  # PROVISIONAL
    "properties": {"interests": {"type": "array"}},
}


@pytest.mark.contract
@pytest.mark.parametrize("case", PROFILE_CASES, ids=[c["id"] for c in PROFILE_CASES])
def test_profile_contract_cases(
    case: dict[str, Any],
    profile_client: Any,
    auth_client: Any,
    logged_in_user: dict[str, Any],
    test_db_state: type[InMemoryState],
    service_mode: str,
):
    """Parametrized contract execution verifying profile endpoints against contract schemas."""
    print(f"\n[Contract Test] Running {case['id']} in {service_mode.upper()} mode")

    headers = logged_in_user["headers"]

    # Precondition for duplicate username: create a second user with the conflicting username
    if case["id"] == "PROF-03-duplicate-username-conflict":
        # Register second user who claims the username "candidate1"
        auth_client.request(
            "POST",
            "/auth/register",  # PROVISIONAL
            json={
                "email": "prior_owner@example.test",
                "password": "PolicyPass123!",  # PROVISIONAL
                "username": "candidate1",
            },
        )

    # Execute HTTP request
    method = case["method"]
    path = case["path"]
    payload = case["payload"]

    response = profile_client.request(method=method, path=path, json=payload, headers=headers)

    # Assert expected HTTP status code
    assert response.status_code == case["expected_status"], (
        f"Case {case['id']} failed: expected {case['expected_status']}, "
        f"got {response.status_code}. Response: {response.text}"
    )

    # Loose schema validation
    data = response.json()
    if case["expected_status"] >= 400:
        validate(instance=data, schema=ERROR_RESPONSE_SCHEMA)
    elif case["id"] == "PROF-01-profile-retrieval-authenticated":
        validate(instance=data, schema=PROFILE_SUCCESS_SCHEMA)
    elif case["id"] == "PROF-04-valid-interest-id-list":
        validate(instance=data, schema=INTERESTS_SUCCESS_SCHEMA)

    # Side-effect assertions for mock mode
    if service_mode == "mock":
        email = logged_in_user["user"]["email"]
        profile_in_db = test_db_state.profiles.get(email, {})

        if case["id"] == "PROF-04-valid-interest-id-list":
            assert profile_in_db.get("interests") == ["tech", "art"]
        elif case["id"] in (
            "PROF-05-unknown-interest-ids",
            "PROF-06-inactive-interest-ids",
            "PROF-07-duplicate-interest-ids",
            "PROF-08-more-than-five-interests",
        ):
            # Assert invalid selection did not touch interests
            assert profile_in_db.get("interests") == []


@pytest.mark.contract
def test_user_cannot_access_another_users_profile(profile_client: Any, two_users: dict[str, Any]):
    """Negative security test: User A must NOT be able to view User B's profile.

    Enforces cross-user authorization boundaries and prevents horizontal privilege escalation.
    """
    user_a = two_users["user_a"]
    user_b = two_users["user_b"]

    # User A tries to access User B's profile by path: /profiles/{user_b_id}
    target_path = f"/profiles/{user_b['user_id']}"  # PROVISIONAL path
    resp = profile_client.request(
        method="GET",
        path=target_path,
        headers=user_a["headers"],  # User A's token
    )

    # Must be forbidden
    assert resp.status_code == 403, f"Expected 403 Forbidden, got {resp.status_code}"
    validate(instance=resp.json(), schema=ERROR_RESPONSE_SCHEMA)


@pytest.mark.contract
def test_invalid_interest_selection_leaves_previous_selections_unchanged(
    profile_client: Any,
    logged_in_user: dict[str, Any],
    test_db_state: type[InMemoryState],
    service_mode: str,
):
    """Negative test: Invalid selection must NOT partially update existing selections (atomicity).

    When a user with valid existing interests attempts an update containing an invalid ID,
    the transaction must abort cleanly with zero mutation to existing interests.
    """
    headers = logged_in_user["headers"]

    # 1. Establish valid initial interests
    initial_payload = {"interest_ids": ["tech", "art"]}
    init_resp = profile_client.request(
        "PUT", "/profiles/me/interests", json=initial_payload, headers=headers  # PROVISIONAL
    )
    assert init_resp.status_code == 200

    # 2. Attempt update containing 1 valid ID and 1 invalid ID
    bad_payload = {"interest_ids": ["music", "invalid_nonexistent_interest"]}
    bad_resp = profile_client.request(
        "PUT", "/profiles/me/interests", json=bad_payload, headers=headers  # PROVISIONAL
    )
    assert bad_resp.status_code == 400

    # 3. Verify in-memory state remained strictly ["tech", "art"]
    if service_mode == "mock":
        email = logged_in_user["user"]["email"]
        current_interests = test_db_state.profiles[email]["interests"]
        assert current_interests == ["tech", "art"], (
            f"Atomic rollback failed: interests were partially modified to {current_interests}"
        )


@pytest.mark.contract
def test_profile_invalid_request_creates_no_partial_records(
    profile_client: Any,
    logged_in_user: dict[str, Any],
    test_db_state: type[InMemoryState],
    service_mode: str,
):
    """Negative test: Malformed profile payloads must not alter state."""
    headers = logged_in_user["headers"]

    bad_payload = {
        "display_name": "Valid Name",
        "illegal_injected_column": "ATTACK_VALUE",
    }
    resp = profile_client.request(
        "PUT", "/profiles/me", json=bad_payload, headers=headers  # PROVISIONAL
    )
    assert resp.status_code == 400

    if service_mode == "mock":
        email = logged_in_user["user"]["email"]
        profile = test_db_state.profiles[email]
        # Ensure display_name was not partially updated
        assert profile.get("display_name") == "", "Partial update detected after rejected request"
