"""
pytest configuration for backend/tests/
========================================
Mirrors the sys.path manipulation that main.py performs when uvicorn starts
so that bare `api.*` and `config` imports resolve correctly from the project
root.

The server is launched from the backend/ directory, which puts backend/ on
sys.path automatically.  pytest is run from the project root (one level up),
so we add backend/ explicitly here.
"""
import sys
from pathlib import Path

# Add backend/ so `from api.deps import ...` and `import config` resolve,
# exactly as they do when uvicorn runs from inside backend/.
_BACKEND_DIR = Path(__file__).resolve().parent.parent          # .../backend
_PROJECT_ROOT = _BACKEND_DIR.parent                            # .../JobApply_Venture

for _p in (_BACKEND_DIR, _PROJECT_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
