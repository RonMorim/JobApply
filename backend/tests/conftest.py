"""
pytest configuration for backend/tests/
========================================
Ensures the project root is on sys.path so the canonical `backend.*` package
path resolves when pytest is run from anywhere.

All intra-backend imports use the `backend.` prefix (see main.py). The bare
`api.*` / `services.*` / `config` forms are forbidden: they load the same
file as a second, independent module object, which breaks monkeypatching and
FastAPI dependency_overrides (the override keys on a different function
object than the one the app actually calls).
"""
import os
import sys
import pytest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # .../JobApply_Venture

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock environment variables for tests."""
    os.environ["ANTHROPIC_API_KEY"] = "test-key-for-ci"
