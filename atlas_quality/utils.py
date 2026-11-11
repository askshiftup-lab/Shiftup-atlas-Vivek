"""Deterministic utility functions for the Atlas quality foundation.

Contains helper functions used across services, quality checks, and contract tests.
"""

from __future__ import annotations

import re
from typing import Any

# Standard E.164 international phone number format: + followed by 7 to 15 digits
E164_REGEX = re.compile(r"^\+[1-9]\d{6,14}$")

# Password complexity regex: min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special character
PASSWORD_COMPLEXITY_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=[\]{};':\"\\|,.<>/?]).{8,128}$"
)


def normalize_username(name: Any) -> str:
    """Normalize a user-provided username for consistent storage and comparisons.

    Performs whitespace stripping and case-folding to lowercase.

    Args:
        name: The username to normalize. Must be a non-empty string.

    Returns:
        The stripped, lowercase username string.

    Raises:
        ValueError: If `name` is not a string, or is empty / contains only whitespace.
    """
    if not isinstance(name, str):
        raise ValueError(f"Username must be a string, got {type(name).__name__}")

    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Username cannot be empty or contain only whitespace")

    return cleaned.lower()


def normalize_phone_number(phone: Any, default_country_code: str = "+91") -> str | None:
    """Normalize and validate a phone number into international E.164 format.

    Strips spaces, hyphens, and punctuation. Rejects invalid or out-of-range phone numbers.

    Args:
        phone: Raw phone string (or None if optional).
        default_country_code: Default country prefix for national numbers (defaults to +91).

    Returns:
        The normalized E.164 phone string (e.g., '+919876543210'), or None if input was empty/None.

    Raises:
        ValueError: If `phone` is not a string, or contains invalid characters.
    """
    if phone is None:
        return None

    if not isinstance(phone, str):
        raise ValueError(f"Phone number must be a string or None, got {type(phone).__name__}")

    stripped = phone.strip()
    if not stripped:
        return None

    # Remove formatting characters commonly found in user input
    cleaned = re.sub(r"[\s\-\(\)\.]", "", stripped)

    if cleaned.startswith("+"):
        candidate = cleaned
    else:
        # If input has no country code prefix, verify digits and apply default country prefix
        digits_only = re.sub(r"\D", "", cleaned)
        if len(digits_only) == 10:
            prefix = (
                default_country_code
                if default_country_code.startswith("+")
                else f"+{default_country_code}"
            )
            candidate = f"{prefix}{digits_only}"
        else:
            raise ValueError(
                f"Phone number '{phone}' must either include an international country code (+) "
                "or be a valid 10-digit number."
            )

    # Validate against E.164 format (+ and 7 to 15 digits)
    if not E164_REGEX.match(candidate):
        raise ValueError(f"Invalid international E.164 phone number format: '{phone}'")

    return candidate


def validate_password_policy(password: Any) -> bool:
    """Validate password against security complexity policies.

    Requires at least 8 characters, at least 1 uppercase letter, at least 1 lowercase letter,
    at least 1 digit, and at least 1 special character.

    Args:
        password: Password string to validate.

    Returns:
        True if valid.

    Raises:
        ValueError: If password fails length or complexity requirements.
    """
    if not isinstance(password, str):
        raise ValueError(f"Password must be a string, got {type(password).__name__}")

    if not PASSWORD_COMPLEXITY_REGEX.match(password):
        raise ValueError(
            "Password does not meet required security policy: must be 8-128 characters and "
            "contain uppercase, lowercase, digit, and special character."
        )

    return True
