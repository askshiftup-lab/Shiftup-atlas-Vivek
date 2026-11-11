"""Unit tests for the sample utility module.

Validates normalize_username, normalize_phone_number, and validate_password_policy
against positive, negative, and edge cases.
All tests are strictly deterministic and marked with `@pytest.mark.unit`.
"""

import pytest

from atlas_quality.utils import (
    normalize_phone_number,
    normalize_username,
    validate_password_policy,
)

# ==============================================================================
# Username Normalization Tests
# ==============================================================================

@pytest.mark.unit
def test_normalize_username_valid():
    """Valid case: mixed-case username with leading/trailing whitespace
    is trimmed and lowercased.
    """
    raw_input = "  VivekIntern2026  "
    expected = "vivekintern2026"
    assert normalize_username(raw_input) == expected


@pytest.mark.unit
@pytest.mark.parametrize("invalid_input", [None, 12345, True, ["user"], {"name": "test"}])
def test_normalize_username_invalid_types(invalid_input):
    """Invalid-input case: non-string types must raise ValueError with clear explanation."""
    with pytest.raises(ValueError, match="Username must be a string"):
        normalize_username(invalid_input)


@pytest.mark.unit
def test_normalize_username_empty_string():
    """Invalid-input case: empty string must raise ValueError."""
    with pytest.raises(ValueError, match="Username cannot be empty"):
        normalize_username("")


@pytest.mark.unit
@pytest.mark.parametrize("whitespace_input", ["   ", "\t", "\n\r  \t\n"])
def test_normalize_username_edge_case_whitespace_only(whitespace_input):
    """Edge case: strings containing only whitespace characters should be rejected as empty."""
    with pytest.raises(ValueError, match="Username cannot be empty"):
        normalize_username(whitespace_input)


@pytest.mark.unit
def test_normalize_username_edge_case_internal_symbols_preserved():
    """Edge case: usernames with internal hyphens, underscores, or numbers
    maintain their internal structure.
    """
    raw_input = "  User_Name.Test-01  "
    expected = "user_name.test-01"
    assert normalize_username(raw_input) == expected


# ==============================================================================
# Phone Number Normalization Tests (Task A & Task C Alignment)
# ==============================================================================

@pytest.mark.unit
@pytest.mark.parametrize(
    "raw_phone, expected",
    [
        ("+1 415-555-2671", "+14155552671"),
        ("+91 98765 43210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("(415) 555-2671", None),  # 10-digit formatted with custom default in test
        (None, None),
        ("   ", None),
    ],
)
def test_normalize_phone_number_cases(raw_phone, expected):
    """Test phone normalization with valid E.164, 10-digit national, and empty/None values."""
    if raw_phone == "(415) 555-2671":
        # 10 digits formatted with parens, should normalize using default +91 prefix
        assert normalize_phone_number(raw_phone, default_country_code="+1") == "+14155552671"
    else:
        assert normalize_phone_number(raw_phone) == expected


@pytest.mark.unit
@pytest.mark.parametrize("invalid_phone", ["123", "not-a-number", "+000000000", "+123"])
def test_normalize_phone_number_invalid_format(invalid_phone):
    """Reject malformed or out-of-range phone numbers."""
    with pytest.raises(ValueError):
        normalize_phone_number(invalid_phone)


@pytest.mark.unit
def test_normalize_phone_number_invalid_type():
    """Reject non-string, non-null values."""
    with pytest.raises(ValueError, match="Phone number must be a string or None"):
        normalize_phone_number(1234567890)


# ==============================================================================
# Password Policy Validation Tests
# ==============================================================================

@pytest.mark.unit
def test_validate_password_policy_valid():
    """Valid case: satisfies length, uppercase, lowercase, digit, and special char."""
    assert validate_password_policy("PolicyPass123!") is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "weak_pwd",
    [
        "short1!",        # too short (< 8)
        "nocapitals123!",  # missing uppercase
        "NOLOWERCASE123!", # missing lowercase
        "NoDigitsHere!!",  # missing digit
        "NoSpecialChar12", # missing special char
    ],
)
def test_validate_password_policy_weak(weak_pwd):
    """Invalid cases: fails individual password policy rules."""
    with pytest.raises(ValueError, match="Password does not meet required security policy"):
        validate_password_policy(weak_pwd)


@pytest.mark.unit
def test_controlled_ci_pipeline_failure_demonstration():
    """Controlled failure test created to demonstrate GitHub Actions CI rejection."""
    assert False, "Controlled failure: proving GitHub Actions CI pipeline blocks failing tests"

