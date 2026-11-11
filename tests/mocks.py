"""In-memory mock clients for Auth and Profile services.

Provides MockAuthClient and MockProfileClient that mimic expected backend behavior
using an in-memory test database. Integrates approved Task A specifications for the
Account & Authentication Service alongside provisional contracts.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from atlas_quality.utils import normalize_phone_number, validate_password_policy


class MockResponse:
    """Mock HTTP response matching the minimal httpx.Response interface."""

    def __init__(self, status_code: int, json_data: dict[str, Any] | list[Any] | None = None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self) -> Any:
        return self._json_data

    @property
    def text(self) -> str:
        return str(self._json_data)


class InMemoryState:
    """Shared in-memory state representing the backing databases for Auth & Profile.

    Reset after every test via pytest fixture teardown to guarantee test isolation.
    """

    # Master catalog of allowed interests and education items
    KNOWN_INTERESTS: set[str] = {
        "tech", "art", "music", "sports", "science", "gaming",
        "interest_tech", "interest_art", "interest_music", "interest_sports",
        "interest_science", "interest_gaming",
    }
    INACTIVE_INTERESTS: set[str] = {
        "archived_crypto", "deprecated_flash", "interest_archived_crypto"
    }
    VALID_EDU_CATEGORIES: set[str] = {
        "undergraduate", "postgraduate", "doctorate", "bootcamp", "puc_11_12", "alumni"
    }
    VALID_INSTITUTIONS: set[str] = {
        "inst_mit", "inst_stanford", "inst_oxford", "inst_iit", "inst_harvard"
    }
    VALID_THEMES: set[str] = {"light", "dark", "system"}

    users: dict[str, dict[str, Any]] = {}
    verification_codes: dict[str, str] = {}
    used_codes: set[tuple[str, str]] = set()  # (email, code)
    verification_attempts: dict[str, int] = {}
    active_tokens: dict[str, str] = {}  # token -> email
    revoked_tokens: set[str] = set()
    password_reset_tokens: dict[str, str] = {}  # token -> email
    profiles: dict[str, dict[str, Any]] = {}  # email -> profile
    onboarding_states: dict[str, dict[str, Any]] = {}  # user_id -> onboarding state

    @classmethod
    def reset(cls) -> None:
        """Completely clear all in-memory tables and state."""
        cls.users.clear()
        cls.verification_codes.clear()
        cls.used_codes.clear()
        cls.verification_attempts.clear()
        cls.active_tokens.clear()
        cls.revoked_tokens.clear()
        cls.password_reset_tokens.clear()
        cls.profiles.clear()
        cls.onboarding_states.clear()


class MockAuthClient:
    """In-memory mock client implementing authentication workflows.

    Implements approved Task A endpoints (/v1/auth/*) and provisional endpoints (/auth/*).
    Exposes a `.request(method, path, json=None, headers=None)` interface compatible
    with httpx.Client.
    """

    # Maximum allowed failed verification attempts before rate limiting / lockout
    MAX_VERIFICATION_ATTEMPTS = 3

    EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    GENERIC_REG_MSG = (
        "If this account can be created, next steps will be sent to its email address."
    )

    def request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> MockResponse:
        """Route incoming HTTP request to internal mock handlers."""
        method_upper = method.upper()
        payload = json or {}
        req_headers = headers or {}

        # 1. Registration (Approved: /v1/auth/registrations, Prov: /auth/register)
        if method_upper == "POST" and path in ("/v1/auth/registrations", "/auth/register"):
            is_v1 = path.startswith("/v1/")
            return self._handle_register(payload, is_v1=is_v1)

        # 2. Initiate Email Verification
        if method_upper == "POST" and path == "/v1/auth/email-verifications":
            return self._handle_request_verification(payload)

        # 3. Resend Email Verification
        if method_upper == "POST" and path == "/v1/auth/email-verifications/resend":
            return self._handle_resend_verification(payload)

        # 4. Confirm Email Verification (Approved /v1/ or Prov /auth/)
        if method_upper == "POST" and path in (
            "/v1/auth/email-verifications/confirm",
            "/auth/verify",
        ):
            is_v1 = path.startswith("/v1/")
            return self._handle_verify(payload, is_v1=is_v1)

        # 5. Sign In / Create Session (Approved: /v1/auth/sessions, Prov: /auth/login)
        if method_upper == "POST" and path in ("/v1/auth/sessions", "/auth/login"):
            is_v1 = path.startswith("/v1/")
            return self._handle_login(payload, is_v1=is_v1)

        # 6. Current Authenticated Session (Approved /v1/ or Prov /auth/)
        if method_upper == "GET" and path in ("/v1/auth/sessions/current", "/auth/session"):
            is_v1 = path.startswith("/v1/")
            return self._handle_session(req_headers, is_v1=is_v1)

        # 7. Session Revocation (Approved: DELETE /v1/auth/sessions/current)
        if method_upper == "DELETE" and path == "/v1/auth/sessions/current":
            return self._handle_revoke_session(req_headers)

        # 8. Password Reset Request (Approved: /v1/auth/password-resets, Prov: /auth/recovery)
        if method_upper == "POST" and path in ("/v1/auth/password-resets", "/auth/recovery"):
            is_v1 = path.startswith("/v1/")
            return self._handle_recovery(payload, is_v1=is_v1)

        # 9. Password Reset Confirm
        if method_upper == "POST" and path == "/v1/auth/password-resets/confirm":
            return self._handle_password_reset_confirm(payload)

        return MockResponse(404, {"error": f"Endpoint not found: {method} {path}"})

    def _handle_register(self, payload: dict[str, Any], is_v1: bool = True) -> MockResponse:
        email = payload.get("email")
        password = payload.get("password")
        first_name = payload.get("first_name") or payload.get("username")
        raw_phone = payload.get("phone") or payload.get("phone_number")

        # Validation: email presence and format
        if not email or not isinstance(email, str) or not self.EMAIL_REGEX.match(email):
            status = 422 if is_v1 else 400
            return MockResponse(status, {"error": "Invalid or missing email format"})

        # Validation: first_name presence (Task A requirement)
        if is_v1 and (not first_name or not isinstance(first_name, str) or not first_name.strip()):
            return MockResponse(422, {"error": "First name is required."})

        # Validation: password presence and policy
        if not password or not isinstance(password, str):
            status = 422 if is_v1 else 400
            return MockResponse(status, {"error": "Password is required."})

        try:
            validate_password_policy(password)
        except ValueError as err:
            status = 422 if is_v1 else 400
            return MockResponse(status, {"error": str(err)})

        # Validation & Normalization: optional phone number (Task A requirement)
        normalized_phone = None
        if raw_phone is not None and str(raw_phone).strip():
            try:
                normalized_phone = normalize_phone_number(raw_phone)
            except ValueError as err:
                status = 422 if is_v1 else 400
                return MockResponse(status, {"error": f"Invalid phone format: {err}"})

        # Check existing user
        if email in InMemoryState.users:
            if is_v1:
                # Anti-enumeration response on collision (Task A)
                return MockResponse(202, {"message": self.GENERIC_REG_MSG})
            return MockResponse(409, {"error": "User with this email already exists"})

        # Create user record (unverified)
        user_id = f"user_{len(InMemoryState.users) + 1}"
        now_str = datetime.now(timezone.utc).isoformat()

        # Security check: client CANNOT elevate account status or set phone_verified_at directly
        InMemoryState.users[email] = {
            "id": user_id,
            "email": email.strip().lower(),
            "first_name": (first_name or "").strip(),
            "password": password,  # in real service this is hashed
            "phone_number": normalized_phone,
            "phone_verified_at": None,  # client cannot set
            "email_verified_at": None,
            "account_status": "pending",  # client cannot override to active
            "is_verified": False,
            "created_at": now_str,
            "updated_at": now_str,
        }

        # Issue deterministic 6-digit verification code
        challenge_code = "123456"
        InMemoryState.verification_codes[email] = challenge_code
        InMemoryState.verification_attempts[email] = 0

        # Auto-create empty profile linked to email
        username_val = payload.get("username") or first_name or user_id
        InMemoryState.profiles[email] = {
            "user_id": user_id,
            "username": username_val,
            "display_name": "",
            "bio": "",
            "interests": [],
            "education": {},
            "theme": "system",
        }

        if is_v1:
            return MockResponse(202, {"message": self.GENERIC_REG_MSG})

        return MockResponse(
            201,
            {
                "message": "User registered successfully. Verification required.",
                "user_id": user_id,
                "is_verified": False,
            },
        )

    def _handle_request_verification(self, payload: dict[str, Any]) -> MockResponse:
        return MockResponse(
            202,
            {"message": "If this account needs verification, a code will be sent."},
        )

    def _handle_resend_verification(self, payload: dict[str, Any]) -> MockResponse:
        return MockResponse(
            202,
            {"message": "If this account needs verification, a new code will be sent."},
        )

    def _handle_verify(self, payload: dict[str, Any], is_v1: bool = True) -> MockResponse:
        email = payload.get("email")
        code = payload.get("code")

        if not email or email not in InMemoryState.users:
            status = 400 if is_v1 else 404
            return MockResponse(status, {"error": "User not found or code invalid."})

        # Verification code format check: 6 digits
        if not code or not isinstance(code, str) or len(code) != 6 or not code.isdigit():
            return MockResponse(400, {"error": "Code must contain exactly 6 digits."})

        attempts = InMemoryState.verification_attempts.get(email, 0)
        # Security rule: rate-limiting / lockout after maximum failed verification attempts
        if attempts >= self.MAX_VERIFICATION_ATTEMPTS:
            status = 400 if is_v1 else 429
            return MockResponse(
                status,
                {"error": "Too many failed attempts. Verification challenge locked."},
            )

        # Check if code is expired / already used for this user account (replay attack protection)
        if (email, code) in InMemoryState.used_codes:
            return MockResponse(400, {"error": "Verification code has already been used"})

        expected_code = InMemoryState.verification_codes.get(email)
        if code != expected_code:
            InMemoryState.verification_attempts[email] = attempts + 1
            return MockResponse(400, {"error": "Invalid verification code entered."})

        # Successful verification: activate user and mark email_verified_at
        user = InMemoryState.users[email]
        user["is_verified"] = True
        user["account_status"] = "active"
        user["email_verified_at"] = datetime.now(timezone.utc).isoformat()
        InMemoryState.used_codes.add((email, code))

        if is_v1:
            return MockResponse(
                200,
                {"message": "Email verified. You can now sign in.", "email": email},
            )

        return MockResponse(200, {"message": "Verification successful. Account is active."})

    def _handle_login(self, payload: dict[str, Any], is_v1: bool = True) -> MockResponse:
        email = payload.get("email")
        password = payload.get("password")

        user = InMemoryState.users.get(email)
        if not user or user.get("password") != password:
            return MockResponse(401, {"error": "Email or password is incorrect."})

        if user.get("account_status") != "active" and not user.get("is_verified", False):
            return MockResponse(403, {"error": "Verify your email address before signing in."})

        # Issue deterministic mock session token
        token = f"mock-token-{user['id']}"
        InMemoryState.active_tokens[token] = email

        if is_v1:
            return MockResponse(
                200,
                {
                    "access_token": token,
                    "token_type": "bearer",
                    "user_id": user["id"],
                    "user": {
                        "user_id": user["id"],
                        "email": user["email"],
                        "first_name": user.get("first_name", ""),
                        "provider": "email",
                    },
                },
            )

        return MockResponse(
            200,
            {
                "access_token": token,
                "token_type": "bearer",
                "user_id": user["id"],
            },
        )

    def _handle_session(self, headers: dict[str, str], is_v1: bool = True) -> MockResponse:
        auth_header = headers.get("Authorization") or headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return MockResponse(
                401, {"error": "Missing or malformed Authorization header"}
            )

        token = auth_header.split(" ", 1)[1]
        if token in InMemoryState.revoked_tokens:
            return MockResponse(401, {"error": "Session has been revoked."})

        email = InMemoryState.active_tokens.get(token)
        if not email or email not in InMemoryState.users:
            return MockResponse(401, {"error": "Invalid or expired session token"})

        user = InMemoryState.users[email]
        if is_v1:
            return MockResponse(
                200,
                {
                    "user": {
                        "user_id": user["id"],
                        "email": user["email"],
                        "first_name": user.get("first_name", ""),
                        "phone_number": user.get("phone_number"),
                        "phone_verified_at": user.get("phone_verified_at"),
                        "email_verified": True,
                        "account_status": user.get("account_status", "active"),
                    },
                    "session": {"token": token},
                },
            )

        return MockResponse(
            200,
            {
                "user_id": user["id"],
                "email": user["email"],
                "is_verified": user["is_verified"],
            },
        )

    def _handle_revoke_session(self, headers: dict[str, str]) -> MockResponse:
        auth_header = headers.get("Authorization") or headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return MockResponse(401, {"error": "Missing or malformed Authorization header"})

        token = auth_header.split(" ", 1)[1]
        if token in InMemoryState.active_tokens:
            del InMemoryState.active_tokens[token]
            InMemoryState.revoked_tokens.add(token)
            return MockResponse(204, None)

        return MockResponse(401, {"error": "Invalid or expired session token"})

    def _handle_recovery(self, payload: dict[str, Any], is_v1: bool = True) -> MockResponse:
        # Anti-enumeration response: uniform message regardless of email existence
        if is_v1:
            return MockResponse(
                202,
                {"message": "If an eligible account exists, a password reset email will be sent."},
            )
        return MockResponse(
            200,
            {"message": "If the email exists in our records, a recovery code has been dispatched."},
        )

    def _handle_password_reset_confirm(self, payload: dict[str, Any]) -> MockResponse:
        token = payload.get("token")
        new_pwd = payload.get("new_password")
        confirm_pwd = payload.get("confirm_password")

        if not token or not new_pwd or new_pwd != confirm_pwd:
            return MockResponse(400, {"error": "Passwords do not match or token missing."})

        try:
            validate_password_policy(new_pwd)
        except ValueError as err:
            return MockResponse(422, {"error": str(err)})

        return MockResponse(200, {"message": "Password successfully reset."})


class MockProfileClient:
    """In-memory mock client implementing profile and interest management workflows.

    Implements approved Task B endpoints (/v1/profile*, /v1/interests, etc.) and
    provisional routes (/profiles/*).
    Exposes a `.request(method, path, json=None, headers=None)` interface compatible
    with httpx.Client.
    """

    MAX_INTERESTS = 5

    def request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> MockResponse:
        """Route incoming HTTP request to internal mock profile handlers."""
        method_upper = method.upper()
        payload = json or {}
        req_headers = headers or {}

        # ------------------------------------------------------------------
        # Public Catalogue & Utility Endpoints (Task B)
        # ------------------------------------------------------------------
        if method_upper == "GET" and path.startswith("/v1/usernames/availability"):
            val = path.split("value=")[-1] if "value=" in path else payload.get("value", "")
            return self._handle_username_availability(val)

        if method_upper == "GET" and path == "/v1/interests":
            return self._handle_get_interests()

        if method_upper == "GET" and path == "/v1/education-categories":
            return self._handle_get_education_categories()

        if method_upper == "GET" and path.startswith("/v1/institutions"):
            return self._handle_get_institutions()

        # ------------------------------------------------------------------
        # Authenticated Profile Endpoints
        # ------------------------------------------------------------------
        current_email, auth_err = self._authenticate(req_headers)
        if auth_err:
            return auth_err

        profile = InMemoryState.profiles.get(current_email)
        if not profile:
            return MockResponse(404, {"error": "Profile record not found"})

        # 1. Retrieve current user profile (Task B: /v1/profile, Prov: /profiles/me)
        if method_upper == "GET" and path in ("/v1/profile", "/profiles/me"):
            return MockResponse(200, profile)

        # 2. Cross-user profile access attempt: /profiles/{user_id} or /v1/profile/{user_id}
        if method_upper == "GET" and (
            path.startswith("/profiles/") or path.startswith("/v1/profile/")
        ):
            target_user_id = (
                path.split("/v1/profile/", 1)[1]
                if path.startswith("/v1/profile/")
                else path.split("/profiles/", 1)[1]
            )
            if target_user_id != profile.get("user_id"):
                return MockResponse(
                    403, {"error": "Forbidden: You cannot access another user's profile"}
                )
            return MockResponse(200, profile)

        # 3. Update permitted profile fields (Task B: PATCH /v1/profile, Prov: PUT /profiles/me)
        if method_upper in ("PUT", "PATCH") and path in ("/v1/profile", "/profiles/me"):
            return self._handle_update_profile(profile, payload)

        # 4. Update interests: /v1/profile/interests or /profiles/me/interests
        if method_upper == "PUT" and "/interests" in path:
            return self._handle_update_interests(profile, payload)

        # 5. Update education: /v1/profile/education or /profiles/me/education
        if method_upper == "PUT" and path in ("/v1/profile/education", "/profiles/me/education"):
            return self._handle_update_education(profile, payload)

        # 6. Update institution: /v1/profile/institution
        if method_upper == "PUT" and path == "/v1/profile/institution":
            return self._handle_update_institution(profile, payload)

        # 7. Update preferences/theme: /v1/profile/preferences or /profiles/me/theme
        if method_upper == "PUT" and path in (
            "/v1/profile/preferences",
            "/profiles/me/theme",
        ):
            return self._handle_update_theme(profile, payload)

        # 8. Onboarding status: /v1/onboarding/status
        if method_upper == "GET" and path == "/v1/onboarding/status":
            uid = profile.get("user_id", "")
            state = InMemoryState.onboarding_states.get(
                uid, {"user_id": uid, "status": "in_progress", "completed_steps": []}
            )
            return MockResponse(200, state)

        # 9. Onboarding step progress: /v1/onboarding/steps/{step}
        if method_upper == "PUT" and path.startswith("/v1/onboarding/steps/"):
            step_key = path.split("/v1/onboarding/steps/", 1)[1]
            uid = profile.get("user_id", "")
            state = InMemoryState.onboarding_states.setdefault(
                uid, {"user_id": uid, "status": "in_progress", "completed_steps": []}
            )
            if step_key not in state["completed_steps"]:
                state["completed_steps"].append(step_key)
            return MockResponse(200, {"user_id": uid, "step": step_key, "status": "completed"})

        return MockResponse(404, {"error": f"Endpoint not found: {method} {path}"})

    def _handle_username_availability(self, val: str) -> MockResponse:
        cleaned = val.strip().lower()
        if not cleaned:
            return MockResponse(400, {"error": "Username value is required."})
        taken = any(
            p.get("username") == cleaned
            for p in InMemoryState.profiles.values()
        )
        return MockResponse(200, {"username": cleaned, "available": not taken})

    def _handle_get_interests(self) -> MockResponse:
        items = [
            {"id": "tech", "slug": "technology", "name": "Technology", "is_active": True},
            {"id": "art", "slug": "art", "name": "Art", "is_active": True},
            {"id": "music", "slug": "music", "name": "Music", "is_active": True},
            {"id": "sports", "slug": "sports", "name": "Sports", "is_active": True},
            {"id": "science", "slug": "science", "name": "Science", "is_active": True},
            {"id": "gaming", "slug": "gaming", "name": "Gaming", "is_active": True},
        ]
        return MockResponse(200, {"items": items})

    def _handle_get_education_categories(self) -> MockResponse:
        items = [
            {"id": "undergraduate", "slug": "undergraduate", "name": "Undergraduate"},
            {"id": "postgraduate", "slug": "postgraduate", "name": "Postgraduate"},
            {"id": "doctorate", "slug": "doctorate", "name": "Doctorate"},
            {"id": "bootcamp", "slug": "bootcamp", "name": "Bootcamp"},
        ]
        return MockResponse(200, {"items": items})

    def _handle_get_institutions(self) -> MockResponse:
        items = [
            {"id": "inst_mit", "name": "MIT", "city": "Cambridge", "country": "US"},
            {"id": "inst_stanford", "name": "Stanford", "city": "Stanford", "country": "US"},
            {"id": "inst_oxford", "name": "Oxford", "city": "Oxford", "country": "UK"},
            {"id": "inst_iit", "name": "IIT", "city": "Delhi", "country": "IN"},
        ]
        return MockResponse(200, {"items": items})

    def _authenticate(self, headers: dict[str, str]) -> tuple[str | None, MockResponse | None]:
        auth_header = headers.get("Authorization") or headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None, MockResponse(401, {"error": "Missing or malformed Authorization header"})

        token = auth_header.split(" ", 1)[1]
        email = InMemoryState.active_tokens.get(token)
        if not email or email not in InMemoryState.users:
            return None, MockResponse(401, {"error": "Invalid or expired session token"})

        return email, None

    def _handle_update_profile(
        self, profile: dict[str, Any], payload: dict[str, Any]
    ) -> MockResponse:
        allowed_keys = {
            "first_name", "display_name", "username", "bio", "education",
            "education_category_id", "institution_id", "avatar_id", "theme", "theme_preference"
        }
        disallowed = [k for k in payload if k not in allowed_keys]
        if disallowed:
            return MockResponse(
                400,
                {"error": f"Disallowed fields in profile update: {', '.join(sorted(disallowed))}"},
            )

        username = payload.get("username")
        theme = payload.get("theme") or payload.get("theme_preference")
        education = payload.get("education")
        cat_id = payload.get("education_category_id")
        inst_id = payload.get("institution_id")

        if username is not None:
            if not isinstance(username, str) or not username.strip():
                return MockResponse(400, {"error": "Username cannot be empty"})

            lowered = username.strip().lower()
            for _existing_email, prof in InMemoryState.profiles.items():
                if prof.get("user_id") != profile["user_id"] and prof.get("username") == lowered:
                    return MockResponse(409, {"error": f"Username '{username}' is already taken"})
            profile["username"] = lowered

        if theme is not None:
            if theme not in InMemoryState.VALID_THEMES:
                return MockResponse(
                    400,
                    {
                        "error": (
                            f"Invalid theme '{theme}'. Must be one of: "
                            f"{', '.join(sorted(InMemoryState.VALID_THEMES))}"
                        )
                    },
                )
            profile["theme"] = theme
            profile["theme_preference"] = theme

        if cat_id is not None:
            if cat_id not in InMemoryState.VALID_EDU_CATEGORIES:
                return MockResponse(400, {"error": f"Unknown education category ID: '{cat_id}'"})
            profile["education_category_id"] = cat_id

        if inst_id is not None:
            if inst_id not in InMemoryState.VALID_INSTITUTIONS:
                return MockResponse(400, {"error": f"Unknown institution ID: '{inst_id}'"})
            profile["institution_id"] = inst_id

        if education is not None:
            e_cat = education.get("category_id")
            e_inst = education.get("institution_id")
            if e_cat and e_cat not in InMemoryState.VALID_EDU_CATEGORIES:
                return MockResponse(400, {"error": f"Unknown education category ID: '{e_cat}'"})
            if e_inst and e_inst not in InMemoryState.VALID_INSTITUTIONS:
                return MockResponse(400, {"error": f"Unknown institution ID: '{e_inst}'"})
            profile["education"] = education

        for field in ("first_name", "display_name", "bio", "avatar_id"):
            if field in payload:
                profile[field] = str(payload[field])

        return MockResponse(200, profile)

    def _handle_update_institution(
        self, profile: dict[str, Any], payload: dict[str, Any]
    ) -> MockResponse:
        inst_id = payload.get("institution_id") or payload.get("id")
        if not inst_id or inst_id not in InMemoryState.VALID_INSTITUTIONS:
            return MockResponse(400, {"error": f"Unknown institution ID: '{inst_id}'"})
        profile["institution_id"] = inst_id
        return MockResponse(200, {"institution_id": inst_id})

    def _handle_update_education(
        self, profile: dict[str, Any], payload: dict[str, Any]
    ) -> MockResponse:
        cat_id = payload.get("category_id")
        inst_id = payload.get("institution_id")

        if not cat_id or cat_id not in InMemoryState.VALID_EDU_CATEGORIES:
            return MockResponse(400, {"error": f"Unknown education category ID: '{cat_id}'"})

        if not inst_id or inst_id not in InMemoryState.VALID_INSTITUTIONS:
            return MockResponse(400, {"error": f"Unknown institution ID: '{inst_id}'"})

        profile["education"] = {"category_id": cat_id, "institution_id": inst_id}
        return MockResponse(200, profile["education"])

    def _handle_update_theme(
        self, profile: dict[str, Any], payload: dict[str, Any]
    ) -> MockResponse:
        theme = payload.get("theme")
        if not theme or theme not in InMemoryState.VALID_THEMES:
            return MockResponse(
                400,
                {
                    "error": (
                        f"Invalid theme '{theme}'. Must be one of: "
                        f"{', '.join(sorted(InMemoryState.VALID_THEMES))}"
                    )
                },
            )
        profile["theme"] = theme
        return MockResponse(200, {"theme": theme})

    def _handle_update_interests(
        self, profile: dict[str, Any], payload: dict[str, Any]
    ) -> MockResponse:
        interests = payload.get("interest_ids")
        if interests is None:
            interests = payload.get("interests")

        if not isinstance(interests, list):
            return MockResponse(400, {"error": "Interests payload must be an array of IDs"})

        if len(interests) > self.MAX_INTERESTS:
            return MockResponse(
                400,
                {
                    "error": (
                        f"Cannot select more than {self.MAX_INTERESTS} interests. "
                        f"Received {len(interests)}."
                    )
                },
            )

        if len(interests) != len(set(interests)):
            return MockResponse(
                400, {"error": "Duplicate interests are not permitted in selection"}
            )

        for item in interests:
            if item in InMemoryState.INACTIVE_INTERESTS:
                return MockResponse(
                    400, {"error": f"Interest '{item}' is currently inactive or deprecated"}
                )
            if item not in InMemoryState.KNOWN_INTERESTS:
                return MockResponse(400, {"error": f"Unknown interest ID: '{item}'"})

        profile["interests"] = list(interests)
        return MockResponse(200, {"user_id": profile["user_id"], "interests": profile["interests"]})
