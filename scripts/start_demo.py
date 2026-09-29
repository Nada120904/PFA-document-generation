"""Start the self-contained local demo API and existing Vite frontend.

Run from any directory with ``python scripts/start_demo.py``.  On first run this
creates a private virtual environment and installs only the demo dependencies.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "chatbot" / "frontend"
VENV = ROOT / ".venv-demo"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REQUIREMENTS = ROOT / "services" / "demo_service" / "requirements.txt"


def run_checked(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def ensure_dependencies() -> None:
    if not PYTHON.exists():
        print("Creating local demo Python environment...")
        venv.create(VENV, with_pip=True)

    marker = VENV / ".requirements-ready"
    if not marker.exists() or marker.stat().st_mtime < REQUIREMENTS.stat().st_mtime:
        print("Installing local demo Python dependencies...")
        run_checked([str(PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS)], ROOT)
        marker.touch()

    if not (FRONTEND / "node_modules" / "vite").exists():
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if npm is None:
            raise RuntimeError("Node.js and npm are required to run the frontend.")
        print("Installing frontend dependencies...")
        run_checked([npm, "ci"], FRONTEND)


def wait_for_api(process: subprocess.Popen[bytes]) -> None:
    for _ in range(80):
        if process.poll() is not None:
            raise RuntimeError("Demo API stopped before becoming ready.")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8015/health", timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise RuntimeError("Demo API did not become ready on port 8015.")


def main() -> None:
    ensure_dependencies()
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required to run the frontend.")

    api_env = os.environ.copy()
    api_env.setdefault("DEMO_DATA_DIR", str(ROOT / "data" / "demo"))
    api = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "services.demo_service.app:app", "--host", "127.0.0.1", "--port", "8015"],
        cwd=ROOT,
        env=api_env,
    )
    frontend: subprocess.Popen[bytes] | None = None
    try:
        wait_for_api(api)
        vite_env = os.environ.copy()
        vite_env["DEMO_API_URL"] = "http://127.0.0.1:8015"
        vite_env["VITE_DEMO_MODE"] = "true"
        frontend = subprocess.Popen(
            [node, str(FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"), "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
            cwd=FRONTEND,
            env=vite_env,
        )
        print("\nLocal demo is ready at http://127.0.0.1:5173")
        print("Press Ctrl+C to stop both processes.\n")
        while api.poll() is None and frontend.poll() is None:
            time.sleep(0.5)
        raise RuntimeError("A demo process stopped unexpectedly.")
    except KeyboardInterrupt:
        pass
    finally:
        for process in (frontend, api):
            if process is not None and process.poll() is None:
                process.terminate()
        for process in (frontend, api):
            if process is not None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    main()
