#!/usr/bin/env python3
"""Install QSys services and configure Chromium kiosk autostart.

Flow:
1. Resolve the service user, release root, runtime paths, and install options.
2. Optionally build the frontend when --build-frontend is explicitly requested.
3. Validate the prebuilt Next.js standalone server expected by production installs.
4. Overwrite .env from .env.example and detected keypad paths unless skipped.
5. Configure Chromium kiosk autostart from the generated PORT unless skipped.
6. Render, install, enable, and restart the qsys systemd services.
"""

from __future__ import annotations

import argparse
import grp
import os
import pwd
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTOSTART_BEGIN = "# >>> QSys Chromium kiosk >>>"
AUTOSTART_END = "# <<< QSys Chromium kiosk <<<"
DEFAULT_PROFILE_DIR = ".config/qsys-chromium"
DEFAULT_DEVICE_DIR = Path("/dev/input/by-path")
DEFAULT_INSTALL_DIR = Path("/etc/systemd/system")
DEFAULT_PORT = "8080"
SERVICE_NAMES = ("qsys-server.service", "qsys-interceptor.service")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Overwrite keypad .env values, configure Chromium kiosk autostart "
            "idempotently, then render and install QSys systemd services."
        )
    )
    parser.add_argument(
        "--user",
        help=(
            "Linux user that owns the kiosk autostart file and runs services. "
            "Default: SUDO_USER when run with sudo, otherwise the current user."
        ),
    )
    parser.add_argument(
        "--chromium-command",
        help="Chromium command to run. Default: chromium, then chromium-browser.",
    )
    parser.add_argument(
        "--autostart-file",
        type=Path,
        help="Autostart file to update. Default: ~<user>/.config/labwc/autostart.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Environment file to overwrite and pass to services. Default: <release-root>/.env.",
    )
    parser.add_argument(
        "--device-dir",
        type=Path,
        default=DEFAULT_DEVICE_DIR,
        help="Input device directory used to generate .env. Default: /dev/input/by-path.",
    )
    parser.add_argument(
        "--device-order",
        default="food,drinks,chicken",
        metavar="ORDER",
        help=(
            "Comma-separated station order passed to update_keypad_env.py when "
            "assigning detected keypads. Default: food,drinks,chicken."
        ),
    )
    parser.add_argument(
        "--skip-chromium",
        action="store_true",
        help="Do not configure Chromium kiosk autostart.",
    )
    parser.add_argument(
        "--skip-env",
        action="store_true",
        help="Do not generate or update .env from the input device directory.",
    )
    parser.add_argument(
        "--build-frontend",
        action="store_true",
        help=(
            "Run pnpm install and pnpm build before installing services. "
            "The normal Pi path uses a prebuilt release artifact instead."
        ),
    )
    parser.add_argument(
        "--systemd-only",
        action="store_true",
        help="Only render/install systemd services. Implies --skip-chromium and --skip-env.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        help="Python executable for the interceptor service. Default: .venv/bin/python, then python3.",
    )
    parser.add_argument(
        "--node",
        type=Path,
        help="Node executable for the Next.js server. Default: node from PATH.",
    )
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=DEFAULT_INSTALL_DIR,
        help="Where rendered service files should be written. Default: /etc/systemd/system.",
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
        help="Print the autostart and service installer changes without writing them.",
    )
    return parser.parse_args()


def service_user(explicit_user: str | None) -> str:
    if explicit_user:
        return explicit_user

    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root":
        return sudo_user

    current_user = pwd.getpwuid(os.getuid()).pw_name
    if current_user != "root":
        return current_user

    raise RuntimeError("Could not infer install user. Pass --user <linux-user>.")


def user_home(user: str) -> Path:
    return Path(pwd.getpwnam(user).pw_dir)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def chromium_command(explicit_command: str | None) -> str:
    if explicit_command:
        return explicit_command

    if shutil.which("chromium"):
        return "chromium"
    if shutil.which("chromium-browser"):
        return "chromium-browser"

    return "chromium"


def kiosk_command(command: str, profile_dir: Path, kiosk_url: str) -> str:
    parts = [
        command,
        "--kiosk",
        f"--user-data-dir={profile_dir}",
        "--autoplay-policy=no-user-gesture-required",
        "--noerrdialogs",
        "--disable-infobars",
        "--no-first-run",
        "--start-maximized",
        "--force-device-scale-factor=1",
        kiosk_url,
    ]
    return " ".join(shlex.quote(part) for part in parts) + " &"


def env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")

    return values


def kiosk_url(env_file: Path, example_file: Path, env_will_be_overwritten: bool) -> str:
    values = env_values(example_file)
    if not env_will_be_overwritten:
        values.update(env_values(env_file))

    port = values.get("PORT", DEFAULT_PORT)
    if not port.isdigit():
        raise RuntimeError(f"PORT must be numeric to generate kiosk URL: {port}")

    return f"http://127.0.0.1:{port}/"


def render_autostart_block(command: str) -> str:
    return "\n".join(
        [
            AUTOSTART_BEGIN,
            command,
            AUTOSTART_END,
        ]
    )


def replace_managed_block(current_text: str, block: str) -> str:
    if AUTOSTART_BEGIN in current_text and AUTOSTART_END in current_text:
        before, rest = current_text.split(AUTOSTART_BEGIN, 1)
        _, after = rest.split(AUTOSTART_END, 1)
        return (before.rstrip() + "\n\n" + block + "\n" + after.lstrip()).strip() + "\n"

    current_text = current_text.rstrip()
    if current_text:
        return current_text + "\n\n" + block + "\n"
    return block + "\n"


def configure_chromium_autostart(
    user: str,
    autostart_file: Path,
    command: str,
    dry_run: bool,
) -> None:
    block = render_autostart_block(command)
    current_text = autostart_file.read_text() if autostart_file.exists() else ""
    next_text = replace_managed_block(current_text, block)

    if dry_run:
        print(f"\n--- {autostart_file} ---")
        print(next_text, end="", flush=True)
        return

    autostart_file.parent.mkdir(parents=True, exist_ok=True)
    autostart_file.write_text(next_text)

    if os.geteuid() == 0:
        user_info = pwd.getpwnam(user)
        os.chown(autostart_file.parent, user_info.pw_uid, user_info.pw_gid)
        os.chown(autostart_file, user_info.pw_uid, user_info.pw_gid)

    print(f"Wrote {autostart_file}")


def update_env_command(args: argparse.Namespace, root: Path, env_file: Path) -> list[str]:
    return [
        sys.executable,
        str(root / "scripts" / "update_keypad_env.py"),
        "--env-file",
        str(env_file),
        "--example-file",
        str(root / ".env.example"),
        "--device-dir",
        str(resolved(args.device_dir)),
        "--order",
        args.device_order,
    ]


def frontend_install_command() -> list[str]:
    return ["pnpm", "install", "--frozen-lockfile"]


def frontend_build_command() -> list[str]:
    return ["pnpm", "build"]


def standalone_server(root: Path) -> Path:
    return root / "frontend" / ".next" / "standalone" / "server.js"


def ensure_standalone_build(root: Path) -> None:
    if standalone_server(root).exists():
        return

    raise RuntimeError(
        "Missing Next.js standalone build. Use a QSys release artifact, or run: "
        "sudo python3 scripts/install.py --build-frontend"
    )


def command_as_user(command: list[str], user: str) -> list[str]:
    if os.geteuid() != 0 or user == "root":
        return command

    sudo = shutil.which("sudo")
    if sudo:
        return [sudo, "-H", "-u", user, "--", *command]

    runuser = shutil.which("runuser")
    if runuser:
        return [runuser, "-u", user, "--", *command]

    raise RuntimeError(
        "Could not find sudo or runuser to run frontend build as the service user."
    )


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


def node_path(explicit_node: Path | None) -> Path:
    if explicit_node:
        return resolved(explicit_node)

    node = shutil.which("node")
    if node:
        return Path(node).resolve()

    raise RuntimeError("Could not find Node. Install Node >= 20.9 or pass --node.")


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
    node: Path,
    env_file: Path,
) -> dict[str, str]:
    replacements = {
        "QSYS_USER": user,
        "QSYS_ROOT": str(root),
        "QSYS_PYTHON": str(python),
        "QSYS_NODE": str(node),
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


def run(command: list[str], dry_run: bool = False) -> None:
    print("+ " + shlex.join(command), flush=True)
    if dry_run:
        return

    subprocess.run(command, check=True)


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

    if dry_run:
        run(["usermod", "-aG", "input", user], dry_run=True)
        print(f"Would add {user} to the input group.", file=sys.stderr)
        return

    run(["usermod", "-aG", "input", user])
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


def run_in(command: list[str], workdir: Path, user: str | None = None) -> None:
    actual_command = command_as_user(command, user) if user else command
    print(
        f"+ cd {shlex.quote(str(workdir))} && {shlex.join(actual_command)}",
        flush=True,
    )
    subprocess.run(actual_command, cwd=workdir, check=True)


def print_run_in(command: list[str], workdir: Path, user: str | None = None) -> None:
    actual_command = command_as_user(command, user) if user else command
    print(
        f"+ cd {shlex.quote(str(workdir))} && {shlex.join(actual_command)}",
        flush=True,
    )


def build_frontend(root: Path, user: str, dry_run: bool) -> None:
    frontend_dir = root / "frontend"
    package_json = frontend_dir / "package.json"

    if not package_json.exists():
        raise RuntimeError(f"Missing frontend package manifest: {package_json}")

    for command in (frontend_install_command(), frontend_build_command()):
        if dry_run:
            print_run_in(command, frontend_dir, user)
        else:
            run_in(command, frontend_dir, user)


def main() -> int:
    args = parse_args()

    try:
        if args.systemd_only:
            args.skip_chromium = True
            args.skip_env = True

        user = service_user(args.user)
        root = REPO_ROOT
        env_file = resolved(args.env_file) if args.env_file else root / ".env"
        example_file = root / ".env.example"

        if needs_root(args) and os.geteuid() != 0:
            raise RuntimeError(
                "Installing QSys system services requires root. Run: "
                "sudo python3 scripts/install.py"
            )

        pwd.getpwnam(user)
        if not root.exists():
            raise RuntimeError(f"QSys root does not exist: {root}")

        python = python_path(root, args.python)
        node = node_path(args.node)
        if not python.exists():
            raise RuntimeError(f"Python executable does not exist: {python}")
        if not node.exists():
            raise RuntimeError(f"Node executable does not exist: {node}")

        if args.build_frontend:
            build_frontend(root, user, args.dry_run)

        if not args.dry_run:
            ensure_standalone_build(root)

        if not args.skip_env:
            command = update_env_command(args, root, env_file)
            if args.dry_run:
                print("+ " + shlex.join(command), flush=True)
            else:
                run(command)
                if env_file.exists() and os.geteuid() == 0:
                    user_info = pwd.getpwnam(user)
                    os.chown(env_file, user_info.pw_uid, user_info.pw_gid)

        if not args.skip_chromium:
            home = user_home(user)
            autostart_file = (
                resolved(args.autostart_file)
                if args.autostart_file
                else home / ".config" / "labwc" / "autostart"
            )
            profile_dir = home / DEFAULT_PROFILE_DIR
            if args.dry_run:
                print(f"+ mkdir -p {shlex.quote(str(profile_dir))}", flush=True)
            else:
                profile_dir.mkdir(parents=True, exist_ok=True)
                if os.geteuid() == 0:
                    user_info = pwd.getpwnam(user)
                    os.chown(profile_dir, user_info.pw_uid, user_info.pw_gid)

            command = kiosk_command(
                chromium_command(args.chromium_command),
                profile_dir,
                kiosk_url(env_file, example_file, not args.skip_env),
            )
            configure_chromium_autostart(user, autostart_file, command, args.dry_run)

        services = rendered_services(root, user, python, node, env_file)

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
