# Security Test Plan & Risk Posture

This document details the security verification strategy for the **Atlas Account & Authentication Service** (aligned with Task A) and the **Profile & Interests Service**. It outlines threat vectors, mitigations, testing methods, and current verification status across the quality pipeline.

---

## 1. Unauthorized & Cross-User Access (BOLA / IDOR)

* **Threat**: An authenticated or unauthenticated attacker accesses another user's private profile or executes unauthorized operations without valid session tokens (Broken Object Level Authorization / IDOR).
* **Mitigation**:
  * Mandatory `Authorization: Bearer <token>` check on all non-public endpoints.
  * Server-side user identity resolution derived strictly from verified JWT/session claims rather than client-supplied path or payload IDs.
* **Testing Method**:
  * Unit/contract tests send requests without headers, with malformed tokens, or with User A's token to User B's `/profiles/{user_b_id}` resource.
* **Status**: **mock-tested** (`test_user_cannot_access_another_users_profile` passes under mock conditions; pending verification against live service implementations).

---

## 2. Phone Number Tampering & E.164 Normalization (Task A Integration)

* **Threat**: Malicious clients attempt to mark phone numbers as verified (`phone_verified_at`) without completing an OTP challenge, elevate account status directly to `active`, or inject unparseable phone formats.
* **Mitigation**:
  * Server normalizes input to international E.164 standard format (`+` followed by country calling code and subscriber digits).
  * Strict anti-tampering: Client-supplied `phone_verified_at`, `email_verified_at`, or `account_status: "active"` fields are ignored or rejected by the server during registration. Status remains strictly `pending` until verification completes.
* **Testing Method**:
  * Contract cases `AUTH-06-invalid-phone-format-v1` and `AUTH-07-client-cannot-set-phone-verified-at`.
  * Dedicated negative test `test_auth_client_tampering_cannot_elevate_status`.
* **Status**: **mock-tested** (Verified in `test_auth_contracts.py` and `tests/mocks.py`).

---

## 3. Generic Recovery & Registration Responses (Anti-Enumeration)

* **Threat**: Attackers query `/v1/auth/password-resets` or `/v1/auth/registrations` with email lists to enumerate valid user accounts based on differentiated response messages or HTTP status codes (e.g. "Email not found" vs "Recovery email sent").
* **Mitigation**:
  * Uniform response contract: regardless of whether the submitted email exists in the database, password recovery returns HTTP 202 with an identical generic message.
  * Duplicate registration returns uniform 202 generic acknowledgement without disclosing existing registration.
* **Testing Method**:
  * Contract cases `AUTH-14-password-reset-generic-response-v1` and `AUTH-15-verification-resend-generic-response-v1` submit registered and unregistered emails, asserting uniform HTTP 202 generic payloads.
* **Status**: **mock-tested** (Verified in `test_auth_contracts.py`).

---

## 4. Rate-Limiting, Cooldown & Lockout Behavior

* **Threat**: Brute-force attacks against verification codes (OTP), sign-in credentials, or resend flood attacks.
* **Mitigation**:
  * Lockout or rate-limiting enforced after consecutive failed verification attempts (e.g., maximum 3 failed attempts before challenge invalidation/lockout).
  * Resend endpoints enforce cooldown intervals.
* **Testing Method**:
  * Dedicated negative test `test_auth_repeated_verification_attempts_blocked_by_rate_limit` sends repeated invalid verification codes until rejection is locked in.
* **Status**: **mock-tested** (Verified in `test_auth_contracts.py`).

---

## 5. Expiration & Replay Protection

* **Threat**: Replay attacks where an intercepted verification code or expired authentication challenge is reused.
* **Mitigation**:
  * Single-use challenge invalidation (marking tokens as consumed immediately upon first valid use) and time-to-live (TTL) expiration.
* **Testing Method**:
  * Contract case `AUTH-09-reused-verification-challenge-v1` asserts that a second verification attempt using an already-consumed code fails with HTTP 400.
* **Status**: **mock-tested** (Verified in `MockAuthClient` and `test_auth_contracts.py`).

---

## 6. Session Revocation & Lifecycle (Sign-out Security)

* **Threat**: Stale or stolen session tokens remaining active after user logs out or terminates session.
* **Mitigation**:
  * `DELETE /v1/auth/sessions/current` explicitly invalidates and revokes the active session token in the database/cache immediately.
* **Testing Method**:
  * Contract case `AUTH-13-session-revocation-v1` and test `test_auth_session_revocation_lifecycle` verify that post-revocation requests return HTTP 401.
* **Status**: **mock-tested** (Verified in `test_auth_contracts.py`).

---

## 7. Secret & Token Redaction from Logs

* **Threat**: Plaintext passwords, authentication tokens, API keys, or personal identifiable information (PII) leak into application server logs, CI logs, or crash traces.
* **Mitigation**:
  * Log sanitizers / custom log formatters masking `password`, `token`, `authorization`, and `code` fields.
  * CI runner log filters ensuring stdout/stderr do not print header dictionaries verbatim.
* **Testing Method**:
  * Log output interception asserting redaction masks (e.g. `[REDACTED]`).
* **Status**: **planned** (Will be validated once live service repositories expose logging adapters).

---

## 8. Dependency Vulnerability Checks (`pip-audit`)

* **Threat**: Known Common Vulnerabilities and Exposures (CVEs) in project dependencies or sub-dependencies.
* **Mitigation**:
  * Dependency pinning in `requirements.txt` and automated auditing using `pip-audit`.
* **Testing Method**:
  * Running `pip-audit -r requirements.txt` locally and in scheduled CI scans.
* **Status**: **planned** (Can be executed locally via `pip install pip-audit && pip-audit`; planned as a scheduled GitHub Actions workflow).

---

## 9. Secret Scanning (`gitleaks`)

* **Threat**: Accidental commit and push of API keys, tokens, or environment credentials into version control.
* **Mitigation**:
  * `.gitignore` excludes `.env` and local credential files.
  * Pre-commit hooks or CI actions running `gitleaks detect` across commit history.
* **Testing Method**:
  * Local git diff scan and CI automated secret scanner.
* **Status**: **planned** (Configured via repository hygiene and `.gitignore`; CI scanning to be activated).

---

## Summary Matrix

| Security Area | Status | Primary Test File / Mechanism |
|---|---|---|
| Unauthorized & Cross-User Access | **mock-tested** | `tests/contracts/test_profile_contracts.py` |
| Phone Number Normalization & Anti-Tampering | **mock-tested** | `tests/contracts/test_auth_contracts.py` (`AUTH-06`, `AUTH-07`) |
| Generic Recovery & Anti-Enumeration | **mock-tested** | `tests/contracts/test_auth_contracts.py` (`AUTH-14`, `AUTH-15`) |
| Rate-Limiting & Lockout | **mock-tested** | `tests/contracts/test_auth_contracts.py` (`test_auth_repeated_verification_attempts...`) |
| Challenge Replay Protection | **mock-tested** | `tests/contracts/test_auth_contracts.py` (`AUTH-09`) |
| Session Revocation & Sign-out | **mock-tested** | `tests/contracts/test_auth_contracts.py` (`AUTH-13`) |
| Token / Log Redaction | **planned** | Service-level logging configuration |
| Dependency Auditing (`pip-audit`) | **planned** | CI pipeline enhancement |
| Secret Scanning (`gitleaks`) | **planned** | Pre-commit & GitHub Action integration |
