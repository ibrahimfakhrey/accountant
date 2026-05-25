#!/usr/bin/env python3
"""Marsoud — first-time setup script.

Run AFTER creating a venv and installing requirements:

    python3 -m venv .venv
    source .venv/bin/activate           # Windows: .venv\\Scripts\\activate
    pip install -r requirements.txt
    python setup.py

What this does:
  1. Copies .env.example → .env if missing
  2. Applies database migrations (creates tables)
  3. Seeds demo data (user, company, chart of accounts, sample partners)

Re-runnable: skips steps that are already done.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.absolute()
RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"; BLUE = "\033[34m"; RESET = "\033[0m"


def step(label):
    print(f"\n{BLUE}→ {label}{RESET}")


def ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg):
    print(f"  {YELLOW}!{RESET} {msg}")


def fail(msg):
    print(f"  {RED}✗ {msg}{RESET}")
    sys.exit(1)


def run(cmd, env=None):
    """Run a shell command, streaming output."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    result = subprocess.run(cmd, cwd=ROOT, env=full_env, shell=isinstance(cmd, str))
    if result.returncode != 0:
        fail(f"Command failed: {cmd}")


def main():
    print(f"{BLUE}╔════════════════════════════════════════╗{RESET}")
    print(f"{BLUE}║  مرصود (Marsoud) — Setup               ║{RESET}")
    print(f"{BLUE}╚════════════════════════════════════════╝{RESET}")

    # Sanity: confirm we're in a venv (recommended but not enforced)
    if sys.prefix == sys.base_prefix:
        warn("Not running inside a virtual environment — strongly recommended to activate one first")

    # ─── Step 1: .env ──────────────────────────────────────────────────
    step("Configuring environment")
    env_path = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if env_path.exists():
        ok(".env already exists — skipping")
    elif env_example.exists():
        shutil.copy(env_example, env_path)
        ok(".env created from .env.example")
        warn("Edit .env to add ANTHROPIC_API_KEY and SMTP settings (optional for dev)")
    else:
        fail(".env.example not found")

    # ─── Step 2: ensure instance/ directory ────────────────────────────
    step("Preparing database directory")
    (ROOT / "instance").mkdir(exist_ok=True)
    ok("instance/ directory ready")

    # ─── Step 3: apply migrations ──────────────────────────────────────
    step("Applying database migrations")
    flask_env = {"FLASK_APP": "flask_app.py"}
    run([sys.executable, "-m", "flask", "db", "upgrade"], env=flask_env)
    ok("Schema is up to date")

    # ─── Step 4: seed demo data ────────────────────────────────────────
    step("Seeding demo data")
    run([sys.executable, str(ROOT / "seed.py")])

    # ─── Done ──────────────────────────────────────────────────────────
    print()
    print(f"{GREEN}{'═' * 50}{RESET}")
    print(f"{GREEN}  ✅ Setup complete — run the server with:{RESET}")
    print(f"{GREEN}{'═' * 50}{RESET}")
    print()
    print(f"     python3 flask_app.py")
    print()
    print(f"  Then open  {BLUE}http://localhost:5050{RESET}")
    print(f"  Login:     demo@manasety.ai / demo1234")
    print()


if __name__ == "__main__":
    main()
