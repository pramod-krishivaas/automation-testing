"""Locate the sibling backend repo.

The suite imports backend modules (Jira attachment, the test_management DB
models, the Java/Android env builder) which live in `automation-testing-backend`
since the mono repo was split. Set BACKEND_REPO_PATH when the two checkouts are
not siblings.
"""

import os
import sys

from dotenv import load_dotenv

# Loaded here rather than relying on a caller, since whichever module imports
# this one first decides whether BACKEND_REPO_PATH is visible.
load_dotenv()

TESTS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BACKEND_ROOT = os.path.abspath(
    os.environ.get("BACKEND_REPO_PATH")
    or os.path.join(TESTS_ROOT, os.pardir, "automation-testing-backend")
)


def ensure_backend_importable() -> str:
    """Put both repo roots on sys.path so `import tests.…` and `import app.…` resolve."""
    for root in (BACKEND_ROOT, TESTS_ROOT):
        if root not in sys.path:
            sys.path.insert(0, root)
    return BACKEND_ROOT
