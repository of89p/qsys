#!/usr/bin/env python3
"""Render and install QSys systemd services for this checkout."""

from __future__ import annotations

import argparse
import getpass
import grp
import os
import pwd
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTALL_DIR = Path("/etc/systemd/system")
DEFAULT_DEVICE_DIR = Path("/dev/input/by-path")
SERVICE_NAMES = ("qsys-server.service", "qsys-interceptor.service")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate qsys-server.service and qsys-interceptor.service with "
            "the correct local paths, then install them into systemd."
        )
    )
    parser.add_argument(
        "--user",
        help=(
            "Linux user that should run the services. Default: SUDO_USER when "
            "run with sudo, otherwise the current user."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="QSys checkout directory. Default: this repository.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        help="Python executable for the services. Default: .venv/bin/python, then python3.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Environment file for the interceptor. Default: <root>/.env.",
    )
    parser.add_argument(
        "--device-dir",
        type=Path,
        default=DEFAULT_DEVICE_DIR,
        help="Input device directory used to generate .env. Default: /dev/input/by-path.",
    )
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=DEFAULT_INSTALL_DIR,
        help="Where rendered service files should be written. Default: /etc/systemd/system.",
    )
    parser.add_argument(
        "--skip-env",
        action="store_true",
        help="Do not generate or update .env from the input device directory.",
    )
    parser.add_argument(
        "--no-input-group",
        action="store_true",
        help="Do not add the service user to the input group.",
    )
    parser.add_argument(
        "--no-enable",
        action="store_true",
        help="Do not enable the services at boot.",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Do not run systemctl daemon-reload after writing service files.",
    )
    parser.add_argument(
        "--no-start",
        action="store_true",
        help="Do not restart the services after installing them.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rendered services and commands without changing the system.",
    )
    return parser.parse_args()


def resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def service_user(explicit_user: str | None) -> str:
    if explicit_user:
        return explicit_user

    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root":
        return sudo_user

    current_user = getpass.getuser()
    if current_user != "root":
        return current_user

    raise RuntimeError("Could not infer service user. Pass --user <linux-user>.")


def python_path(root: Path, explicit_python: Path | None) -> Path:
    if explicit_python:
        return resolved(explicit_python)

    venv_python = root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python

    python3 = shutil.which("python3")
    if python3:
        return Path(python3).resolve()

    raise RuntimeError("Could not find Python. Create .venv or pass --python.")


def reject_whitespace(label: str, value: str) -> None:
    if any(character.isspace() for character in value):
        raise RuntimeError(
            f"{label} contains whitespace, which this installer does not support: {value}"
        )


def render_template(template: Path, replacements: dict[str, str]) -> str:
    text = template.read_text()
    for placeholder, value in replacements.items():
        text = text.replace("{{" + placeholder + "}}", value)

    if "{{" in text or "}}" in text:
        raise RuntimeError(f"Unresolved placeholder in {template}")

    return text


def rendered_services(
    root: Path,
    user: str,
    python: Path,
    env_file: Path,
) -> dict[str, str]:
    replacements = {
        "QSYS_USER": user,
        "QSYS_ROOT": str(root),
        "QSYS_PYTHON": str(python),
        "QSYS_ENV_FILE": str(env_file),
    }

    for label, value in replacements.items():
        reject_whitespace(label, value)

    services: dict[str, str] = {}
    for service_name in SERVICE_NAMES:
        template = root / "systemd" / f"{service_name}.template"
        if not template.exists():
            raise RuntimeError(f"Missing template: {template}")
        services[service_name] = render_template(template, replacements)

    return services


def needs_root(args: argparse.Namespace) -> bool:
    if args.dry_run:
        return False

    install_dir = resolved(args.install_dir)
    installs_to_system = install_dir == DEFAULT_INSTALL_DIR
    changes_systemd = not args.no_reload or not args.no_enable or not args.no_start
    changes_groups = not args.no_input_group

    return installs_to_system or changes_systemd or changes_groups


def run(command: list[str], dry_run: bool) -> None:
    if dry_run:
        print("+ " + shlex.join(command))
        return

    subprocess.run(command, check=True)


def update_env_file(
    root: Path,
    env_file: Path,
    device_dir: Path,
    user: str,
    dry_run: bool,
) -> None:
    script = root / "scripts" / "update_env_from_ls.py"
    command = [
        sys.executable,
        str(script),
        "--env-file",
        str(env_file),
        "--example-file",
        str(root / ".env.example"),
        "--device-dir",
        str(device_dir),
    ]

    if dry_run:
        print("+ " + shlex.join(command))
        return

    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print(
            f"Warning: could not update .env from {device_dir}. "
            "You can rerun scripts/update_env_from_ls.py after plugging in keypads.",
            file=sys.stderr,
        )
        return

    if env_file.exists() and os.geteuid() == 0:
        user_info = pwd.getpwnam(user)
        os.chown(env_file, user_info.pw_uid, user_info.pw_gid)


def ensure_input_group(user: str, dry_run: bool) -> None:
    try:
        input_group = grp.getgrnam("input")
    except KeyError:
        print("Warning: input group does not exist on this system.", file=sys.stderr)
        return

    user_info = pwd.getpwnam(user)
    already_primary = user_info.pw_gid == input_group.gr_gid
    already_member = user in input_group.gr_mem
    if already_primary or already_member:
        return

    run(["usermod", "-aG", "input", user], dry_run)
    print(
        f"Added {user} to the input group. Log out and back in if running manually.",
        file=sys.stderr,
    )


def install_services(
    services: dict[str, str],
    install_dir: Path,
    dry_run: bool,
) -> None:
    if dry_run:
        for service_name, text in services.items():
            print(f"\n--- {install_dir / service_name} ---")
            print(text, end="" if text.endswith("\n") else "\n")
        return

    install_dir.mkdir(parents=True, exist_ok=True)
    for service_name, text in services.items():
        service_path = install_dir / service_name
        service_path.write_text(text)
        service_path.chmod(0o644)
        print(f"Wrote {service_path}")


def main() -> int:
    args = parse_args()

    try:
        user = service_user(args.user)
        root = resolved(args.root)
        python = python_path(root, args.python)
        env_file = resolved(args.env_file) if args.env_file else root / ".env"
        device_dir = resolved(args.device_dir)

        if needs_root(args) and os.geteuid() != 0:
            raise RuntimeError(
                "Installing system services requires root. Run: "
                "sudo python3 scripts/install_systemd_services.py"
            )

        pwd.getpwnam(user)
        if not root.exists():
            raise RuntimeError(f"QSys root does not exist: {root}")
        if not python.exists():
            raise RuntimeError(f"Python executable does not exist: {python}")

        services = rendered_services(root, user, python, env_file)

        if not args.skip_env:
            update_env_file(root, env_file, device_dir, user, args.dry_run)
        if not args.no_input_group:
            ensure_input_group(user, args.dry_run)

        install_services(services, resolved(args.install_dir), args.dry_run)

        if not args.no_reload:
            run(["systemctl", "daemon-reload"], args.dry_run)
        if not args.no_enable:
            run(["systemctl", "enable", *SERVICE_NAMES], args.dry_run)
        if not args.no_start:
            run(["systemctl", "restart", *SERVICE_NAMES], args.dry_run)

    except (OSError, RuntimeError, subprocess.CalledProcessError, KeyError) as exc:
        print(f"Install failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
