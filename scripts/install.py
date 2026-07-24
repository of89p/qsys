#!/usr/bin/env python3
"""Install QSys services and configure Chromium kiosk autostart."""

from __future__ import annotations

import argparse
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
DEFAULT_KIOSK_URL = "http://127.0.0.1:8080/"
DEFAULT_PROFILE_DIR = ".config/qsys-chromium"
DEFAULT_DEVICE_DIR = Path("/dev/input/by-path")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Update keypad .env values, configure Chromium kiosk autostart "
            "idempotently, then run scripts/install_systemd_services.py."
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
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="QSys checkout directory. Default: this repository.",
    )
    parser.add_argument(
        "--kiosk-url",
        default=DEFAULT_KIOSK_URL,
        help=f"URL opened by Chromium kiosk. Default: {DEFAULT_KIOSK_URL}",
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
        help="Environment file to update and pass to services. Default: <root>/.env.",
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
        help="Only run the systemd service installer.",
    )
    parser.add_argument(
        "--skip-env",
        action="store_true",
        help="Do not generate or update .env from the input device directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the autostart and service installer changes without writing them.",
    )
    parser.add_argument(
        "service_args",
        nargs=argparse.REMAINDER,
        help=(
            "Arguments passed through to install_systemd_services.py. Prefix with "
            "-- if the first pass-through argument starts with '-'."
        ),
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


def update_env_command(args: argparse.Namespace, env_file: Path) -> list[str]:
    return [
        sys.executable,
        str(resolved(args.root) / "scripts" / "update_keypad_env.py"),
        "--env-file",
        str(env_file),
        "--example-file",
        str(resolved(args.root) / ".env.example"),
        "--device-dir",
        str(resolved(args.device_dir)),
        "--order",
        args.device_order,
    ]


def service_installer_command(args: argparse.Namespace, user: str) -> list[str]:
    service_args = list(args.service_args)
    if service_args and service_args[0] == "--":
        service_args = service_args[1:]

    command = [
        sys.executable,
        str(resolved(args.root) / "scripts" / "install_systemd_services.py"),
        "--user",
        user,
        "--root",
        str(resolved(args.root)),
        "--env-file",
        str(resolved(args.env_file) if args.env_file else resolved(args.root) / ".env"),
    ]

    if args.dry_run and "--dry-run" not in service_args:
        command.append("--dry-run")

    return [*command, *service_args]


def run(command: list[str]) -> None:
    print("+ " + shlex.join(command), flush=True)
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()

    try:
        user = service_user(args.user)
        home = user_home(user)
        autostart_file = (
            resolved(args.autostart_file)
            if args.autostart_file
            else home / ".config" / "labwc" / "autostart"
        )
        profile_dir = home / DEFAULT_PROFILE_DIR
        env_file = resolved(args.env_file) if args.env_file else resolved(args.root) / ".env"

        if not args.skip_chromium:
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
                args.kiosk_url,
            )
            configure_chromium_autostart(user, autostart_file, command, args.dry_run)

        if not args.skip_env:
            command = update_env_command(args, env_file)
            if args.dry_run:
                print("+ " + shlex.join(command), flush=True)
            else:
                run(command)
                if env_file.exists() and os.geteuid() == 0:
                    user_info = pwd.getpwnam(user)
                    os.chown(env_file, user_info.pw_uid, user_info.pw_gid)

        run(service_installer_command(args, user))
    except (OSError, RuntimeError, subprocess.CalledProcessError, KeyError) as exc:
        print(f"Install failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
