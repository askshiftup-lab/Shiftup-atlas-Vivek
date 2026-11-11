# Atlas Quality Engineering & Contract Testing Foundation

[![CI Pipeline](https://github.com/askshiftup-lab/Shiftup-atlas-Vivek/actions/workflows/ci.yml/badge.svg)](https://github.com/askshiftup-lab/Shiftup-atlas-Vivek/actions/workflows/ci.yml)

This repository provides an automated quality pipeline, testing harness, and API contract-testing framework for the **Account/Auth** and **Profile/Interests** services of Project Atlas.

Because the actual services are actively being built in separate repositories by other interns and the finalized API contracts have not yet been approved, this repository implements a **provisional, mock-based testing architecture**. It allows quality assurance, linting, test patterns, and continuous integration to be fully established and verified ahead of time.

---

## 1. Architecture & Design Principles

* **Zero External Dependencies**: All tests run deterministically with synthetic data. No external network access, real emails, or production databases are required.
* **Provisional Design**: Any anticipated endpoint, HTTP status code, payload schema, or password policy is explicitly marked as `# PROVISIONAL` (or `"provisional": true` in JSON) so they can be easily identified and updated once approved contracts arrive.
* **Test Isolation**: A shared in-memory test database resets automatically after every single test using pytest fixtures, preventing test pollution.
* **Transparent Modes (Mock vs Real)**: Tests automatically run against in-memory mocks (`MockAuthClient` and `MockProfileClient`) by default. If live service URLs are configured, tests seamlessly switch to live HTTP communication via `httpx.Client`.
* **Strict Honesty Guard**: Live integration tests will **never** claim to have passed when running on mocks; they are explicitly **SKIPPED** unless valid service URLs are provided.

---

## 2. Repository Structure

```text
atlas-quality-foundation/
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI workflow
├── atlas_quality/
│   ├── __init__.py
│   └── utils.py                 # Pure utility function (normalize_username)
├── docs/
│   ├── security-test-plan.md    # Security risk coverage and roadmap
│   └── test-report-template.md  # Daily submission & test report template
├── tests/
│   ├── conftest.py              # Pytest fixtures, test DB cleanup, client modes
│   ├── mocks.py                 # In-memory MockAuthClient & MockProfileClient
│   ├── unit/
│   │   └── test_sample.py       # Unit tests for atlas_quality.utils
│   ├── contracts/
│   │   ├── test_auth_contracts.py    # Auth contract verification & negative tests
│   │   └── test_profile_contracts.py # Profile contract verification & negative tests
│   ├── fixtures/
│   │   └── synthetic_payloads.json   # Contract cases, schemas, and side effects
│   └── integration/
│       ├── README.md            # Guide to running integration against live services
│       └── test_integration_smoke.py # Skipped unless live URLs are configured
├── .env.example                 # Template for local service URLs
├── .gitignore                   # Ignore rules for venv, caches, and secrets
├── pyproject.toml               # Pytest and Ruff linter configurations
├── requirements.txt             # Pinned dependency manifest
└── README.md                    # Project documentation
```

---

## 3. Getting Started & Local Setup

### Step 1: Create and Activate a Virtual Environment

On Windows (PowerShell):
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 4. Running Quality Checks & Tests

### Linting with Ruff
Ruff enforces code quality, style consistency, import sorting, and syntax correctness:
```bash
ruff check .
```
To automatically fix formatting or sort imports:
```bash
ruff check --fix .
```

### Running Pytest
Run the entire test suite with detailed output:
```bash
pytest
```

### Running Specific Test Categories by Marker
Use pytest markers to execute targeted subsets of tests:

```bash
# 1. Run Unit Tests Only
pytest -m unit

# 2. Run API Contract Tests Only
pytest -m contract

# 3. Run Live Integration Smoke Tests Only
pytest -m integration
```

---

## 5. Mock Mode vs Live Service Mode

| Test Suite | Default (Mock Mode) | With Real URLs Set | Trigger Requirement |
|---|---|---|---|
| **Unit Tests** (`tests/unit/`) | **PASSED** | **PASSED** | Local Python execution |
| **Auth Contract Tests** (`tests/contracts/test_auth_contracts.py`) | **PASSED** (via `MockAuthClient`) | **PASSED / TESTED** | `MockAuthClient` by default |
| **Profile Contract Tests** (`tests/contracts/test_profile_contracts.py`) | **PASSED** (via `MockProfileClient`) | **PASSED / TESTED** | `MockProfileClient` by default |
| **Integration Smoke Tests** (`tests/integration/test_integration_smoke.py`) | **SKIPPED** | **EXECUTED** | Requires `ATLAS_AUTH_URL` & `ATLAS_PROFILE_URL` |

### Pointing to Live Services
When the other interns launch their service repos locally:
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Set the service URLs:
   ```env
   ATLAS_AUTH_URL=http://localhost:8001
   ATLAS_PROFILE_URL=http://localhost:8002
   ```
3. Run integration smoke tests:
   ```bash
   pytest -m integration
   ```

> **HONESTY NOTE**:
> A passing result in mock mode validates the testing framework, test schemas, and assertion logic. It does **NOT** validate that the other interns' services are working. Service integration must only be reported as verified once live integration tests pass against running deployments.

---

## 6. Continuous Integration (GitHub Actions)

The `.github/workflows/ci.yml` pipeline triggers automatically on:
- Every push to the `main` branch.
- Every pull request targeting the `main` branch.

It enforces:
1. Clean environment setup on Python 3.12 with pip caching.
2. Installation of pinned dependencies from `requirements.txt`.
3. Ruff linting checks (`ruff check .`).
4. Full pytest execution (`pytest`).
5. Zero secrets access and minimal read-only permissions (`contents: read`).
