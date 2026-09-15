"""Reading the suite's test sources: which pytest functions a file defines, and
which files a test-type folder holds.

This runs here because the sources are here; the backend asks for it over the
runner connection. AST-based rather than regex-over-text, so commented-out
@allure.title(...) lines are ignored.
"""

import ast
import os
import re
from pathlib import Path

from runner.errors import RunnerError

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"

_ID_PATTERN = re.compile(r"^\s*([A-Za-z]{1,4}_\d{2,4})\s*--?\s*(.*)$")

# Leading pytest/catalog prefix stripped when matching a source function name to a
# DB testcase_key. MUST stay in lockstep with the backend's copy
# (app/modules/test_management/discovery.py) and the frontend's `normalizeFuncKey`
# (TestScreen.jsx): `test_LOGINPOS_TC_029` and `LOGINPOS_TC_029` both reduce to
# `loginpos_tc_029`.
_MATCH_PREFIX = re.compile(r"^(tc|test)_")


def normalize_match_key(name: str) -> str:
    """Reduce a testcase_key or a source `def` name to a common comparison key."""
    return _MATCH_PREFIX.sub("", (name or "").strip().lower())


def _resolve_safe_path(relative_path: str) -> Path:
    """Resolve a repo-relative path, rejecting anything outside tests/."""
    candidate = (REPO_ROOT / relative_path).resolve()
    if candidate.suffix != ".py":
        raise RunnerError(400, "Only .py files can be inspected")
    if not candidate.is_relative_to(TESTS_DIR):
        raise RunnerError(400, "Path must be inside tests/")
    if not candidate.is_file():
        raise RunnerError(404, f"File not found: {relative_path}")
    return candidate


def _extract_allure_title(decorator_list: list[ast.expr]) -> str | None:
    for dec in decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == "title"
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "allure"
            and dec.args
            and isinstance(dec.args[0], ast.Constant)
            and isinstance(dec.args[0].value, str)
        ):
            return dec.args[0].value
    return None


def discover_automation_tests(relative_path: str) -> list[dict]:
    """Every pytest-collectable test function in a repo-relative .py file under tests/.

    Returns {id, title, function_name, line, match_key} per function. When the
    function's @allure.title is "ID -- description", `id` and a cleaned `title`
    are split out; otherwise `id` is None and `title` is the raw title (or "").
    """
    absolute_path = _resolve_safe_path(relative_path)
    tree = ast.parse(absolute_path.read_text(encoding="utf-8"), filename=str(absolute_path))

    results: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # pytest's default collection prefix — mirror it so we list exactly what runs.
        if not node.name.startswith("test"):
            continue

        raw_title = _extract_allure_title(node.decorator_list)
        tc_id: str | None = None
        title = raw_title or ""
        if raw_title:
            match = _ID_PATTERN.match(raw_title)
            if match:
                tc_id = match.group(1).upper()
                title = match.group(2).strip()

        results.append({
            "id": tc_id,
            "title": title,
            "function_name": node.name,
            "line": node.lineno,
            "match_key": normalize_match_key(node.name),
        })
    return results


def discover_type_folder(type_label: str) -> list[dict]:
    """Every test function physically under tests/test_suites/<type>/.

    The folder location is the type authority for these tests. Each item adds
    `file` (repo-relative path) and `app` (the per-app subfolder name).
    """
    from tests.test_type_config import folder_for_type

    folder = folder_for_type(type_label)
    if not folder or not os.path.isdir(folder):
        return []

    folder_abs = os.path.abspath(folder)
    results: list[dict] = []
    for root, _dirs, files in os.walk(folder_abs):
        for fname in sorted(files):
            if not (fname.startswith("test_") and fname.endswith(".py")):
                continue
            abs_path = os.path.join(root, fname)
            rel = os.path.relpath(abs_path, REPO_ROOT).replace("\\", "/")
            sub = os.path.relpath(abs_path, folder_abs).replace("\\", "/")
            app = sub.split("/")[0] if "/" in sub else ""
            try:
                for fn in discover_automation_tests(rel):
                    results.append({**fn, "file": rel, "app": app})
            except Exception:
                continue  # skip a file that fails to parse rather than fail the whole view
    return results
