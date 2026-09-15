"""Finding the Android and Java tooling on this machine.

adb and a JDK are often missing from PATH for a given process (a secondary
Windows account, or a process started before an installer updated PATH) even
though they work in a terminal. So they are resolved explicitly and injected into
the environment Appium and Allure are launched with.
"""

import os
import shutil
import socket

# conftest.py connects the Appium driver to this port.
APPIUM_PORT = 4723
ALLURE_CMD = os.getenv("ALLURE_CMD") or r"C:\Users\Pramo\scoop\shims\allure"


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def resolve_adb_path() -> str:
    """PATH, then ANDROID_HOME / ANDROID_SDK_ROOT, then Android Studio's default SDK location."""
    found = shutil.which("adb")
    if found:
        return found

    for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk_root = os.environ.get(env_var)
        if sdk_root:
            candidate = os.path.join(sdk_root, "platform-tools", "adb.exe" if os.name == "nt" else "adb")
            if os.path.isfile(candidate):
                return candidate

    if os.name == "nt":
        default = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"
        )
        if os.path.isfile(default):
            return default

    return "adb"


ADB_PATH = resolve_adb_path()


def _has_java(home: str) -> bool:
    if not home:
        return False
    exe = "java.exe" if os.name == "nt" else "java"
    return os.path.isfile(os.path.join(home, "bin", exe))


def resolve_java_home() -> str | None:
    """JAVA_HOME, then java on PATH, then Android Studio's bundled JBR, then common JDK roots.

    UiAutomator2 verifies APK signatures with Java; without it Appium fails with
    "java.exe could not be found neither in PATH nor under JAVA_HOME".
    """
    jh = os.environ.get("JAVA_HOME")
    if _has_java(jh):
        return jh

    found = shutil.which("java")
    if found:
        # …/jbr/bin/java(.exe) -> …/jbr
        home = os.path.dirname(os.path.dirname(found))
        if _has_java(home):
            return home

    candidates: list[str] = []
    if os.name == "nt":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        lad = os.environ.get("LOCALAPPDATA", "")
        candidates += [
            os.path.join(pf, "Android", "Android Studio", "jbr"),
            os.path.join(lad, "Programs", "Android Studio", "jbr"),
        ]
        for base in (os.path.join(pf, "Java"),
                     os.path.join(pf, "Eclipse Adoptium"),
                     os.path.join(pf, "Microsoft")):
            if os.path.isdir(base):
                for name in sorted(os.listdir(base), reverse=True):
                    candidates.append(os.path.join(base, name))

    for c in candidates:
        if _has_java(c):
            return c

    return None


JAVA_HOME = resolve_java_home()


def _sdk_root_from_adb() -> str | None:
    """Derive the Android SDK root from the resolved adb path (…/platform-tools/adb)."""
    if ADB_PATH and os.path.basename(os.path.dirname(ADB_PATH)).lower() == "platform-tools":
        return os.path.dirname(os.path.dirname(ADB_PATH))
    return os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")


def build_tool_env() -> dict:
    """The current environment with JAVA_HOME / ANDROID_HOME set and their bin dirs on PATH."""
    env = os.environ.copy()
    path_parts = [env.get("PATH", "")]

    if JAVA_HOME:
        env["JAVA_HOME"] = JAVA_HOME
        path_parts.insert(0, os.path.join(JAVA_HOME, "bin"))

    sdk_root = _sdk_root_from_adb()
    if sdk_root and os.path.isdir(sdk_root):
        env["ANDROID_HOME"] = sdk_root
        env.setdefault("ANDROID_SDK_ROOT", sdk_root)
        path_parts.insert(0, os.path.join(sdk_root, "platform-tools"))

    env["PATH"] = os.pathsep.join(p for p in path_parts if p)
    return env
