#!/usr/bin/env python3
"""Update .env keypad paths from `ls -l /dev/input/by-path/` output."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICE_DIR = Path("/dev/input/by-path")
EXCLUDED_DEVICE_PATHS = (
    Path("/dev/input/by-id/usb-Keychron_Keychron_K6-event-kbd"),
    Path("/dev/input/by-id/usb-Logitech_USB_Keyboard-event-kbd"),
)

DEVICE_ENV_KEYS = ("FOOD_DEVICE_PATH", "DRINKS_DEVICE_PATH", "CHICKEN_DEVICE_PATH")
STATION_ENV_KEYS = {
    "food": "FOOD_DEVICE_PATH",
    "drinks": "DRINKS_DEVICE_PATH",
    "chicken": "CHICKEN_DEVICE_PATH",
}


def parse_device_order(raw_order: str) -> tuple[str, ...]:
    parts = [part.strip() for part in raw_order.split(",") if part.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("order must include at least one station")

    order: list[str] = []
    for part in parts:
        env_key = STATION_ENV_KEYS.get(part.lower(), part.upper())
        if env_key not in DEVICE_ENV_KEYS:
            valid = ", ".join((*STATION_ENV_KEYS, *DEVICE_ENV_KEYS))
            raise argparse.ArgumentTypeError(
                f"unknown station/env key {part!r}; expected one of: {valid}"
            )
        if env_key in order:
            raise argparse.ArgumentTypeError(f"duplicate station/env key: {part}")
        order.append(env_key)

    return tuple(order)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find *-event-kbd devices in ls output and write FOOD_DEVICE_PATH, "
            "DRINKS_DEVICE_PATH, and CHICKEN_DEVICE_PATH into .env."
        )
    )
    parser.add_argument(
        "--device-dir",
        type=Path,
        default=DEFAULT_DEVICE_DIR,
        help="Input device directory to list. Default: /dev/input/by-path",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=REPO_ROOT / ".env",
        help="Environment file to update. Default: repo .env",
    )
    parser.add_argument(
        "--example-file",
        type=Path,
        default=REPO_ROOT / ".env.example",
        help="Template to copy from when .env does not exist. Default: repo .env.example",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--from-file",
        type=Path,
        help="Read saved ls output instead of running ls.",
    )
    source.add_argument(
        "--stdin",
        action="store_true",
        help="Read ls output from standard input.",
    )
    parser.add_argument(
        "--swap",
        action="store_true",
        help=(
            "Swap the first two detected keyboard devices before applying --order. "
            "Kept for older two-keypad Food/Drinks setups."
        ),
    )
    parser.add_argument(
        "--order",
        type=parse_device_order,
        default=DEVICE_ENV_KEYS,
        metavar="ORDER",
        help=(
            "Comma-separated assignment order for detected keyboard devices. "
            "Accepts station names or env keys. Default: food,drinks,chicken."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the .env content that would be written without changing files.",
    )
    return parser.parse_args()


def read_ls_output(args: argparse.Namespace) -> str:
    if args.from_file:
        return args.from_file.read_text()

    if args.stdin:
        return sys.stdin.read()

    result = subprocess.run(
        ["ls", "-l", str(args.device_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ls command failed")

    return result.stdout


def resolved_path(path: Path) -> Path | None:
    try:
        return path.resolve()
    except OSError:
        return None


def symlink_target(path: Path) -> str | None:
    try:
        return os.readlink(path)
    except OSError:
        return None


def excluded_device_keys() -> set[str]:
    keys: set[str] = set()

    for excluded_path in EXCLUDED_DEVICE_PATHS:
        keys.add(str(excluded_path))
        keys.add(excluded_path.name)

        target = symlink_target(excluded_path)
        if target:
            keys.add(target)

        resolved = resolved_path(excluded_path)
        if resolved:
            keys.add(str(resolved))

    return keys


def is_excluded_keyboard(
    link_path: Path,
    link_name: str,
    link_target: str,
    excluded_keys: set[str],
) -> bool:
    if str(link_path) in excluded_keys or link_name in excluded_keys:
        return True

    if link_target in excluded_keys:
        return True

    resolved = resolved_path(link_path)
    return resolved is not None and str(resolved) in excluded_keys


def parse_keyboard_paths(ls_output: str, device_dir: Path) -> list[str]:
    paths: list[str] = []
    excluded_keys = excluded_device_keys()

    for raw_line in ls_output.splitlines():
        if " -> " not in raw_line:
            continue

        before_arrow, link_target = raw_line.split(" -> ", 1)
        before_arrow = before_arrow.strip()
        link_target = link_target.strip()
        if not before_arrow:
            continue

        link_name = before_arrow.split()[-1]
        if not link_name.endswith("-event-kbd"):
            continue

        link_path = Path(link_name)
        if not link_path.is_absolute():
            link_path = device_dir / link_path

        if is_excluded_keyboard(link_path, link_name, link_target, excluded_keys):
            continue

        path = str(link_path)
        if path not in paths:
            paths.append(path)

    return paths


def env_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None

    key = stripped.split("=", 1)[0].strip()
    return key or None


def set_env_values(lines: list[str], values: dict[str, str]) -> list[str]:
    updated: list[str] = []
    written: set[str] = set()

    for line in lines:
        key = env_key(line)
        if key in values:
            if key not in written:
                updated.append(f"{key}={values[key]}")
                written.add(key)
            continue
        updated.append(line)

    missing = [key for key in values if key not in written]
    if missing:
        if updated and updated[-1].strip():
            updated.append("")
        for key in missing:
            updated.append(f"{key}={values[key]}")

    return updated


def load_env_lines(env_file: Path, example_file: Path) -> list[str]:
    if env_file.exists():
        return env_file.read_text().splitlines()

    if example_file.exists():
        return example_file.read_text().splitlines()

    return []


def build_env_text(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()

    try:
        ls_output = read_ls_output(args)
    except OSError as exc:
        print(f"Could not read ls output: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Could not run ls: {exc}", file=sys.stderr)
        return 1

    keyboard_paths = parse_keyboard_paths(ls_output, args.device_dir)
    if args.swap and len(keyboard_paths) >= 2:
        keyboard_paths[0], keyboard_paths[1] = keyboard_paths[1], keyboard_paths[0]

    if not keyboard_paths:
        print(
            f"No usable *-event-kbd devices found. Run `ls -l {args.device_dir}/` "
            "and confirm the keypad is connected. The Keychron dev keyboard is "
            "excluded automatically.",
            file=sys.stderr,
        )
        return 1

    device_values = dict.fromkeys(DEVICE_ENV_KEYS, "")
    for env_key, keyboard_path in zip(args.order, keyboard_paths):
        device_values[env_key] = keyboard_path

    lines = load_env_lines(args.env_file, args.example_file)
    lines = set_env_values(lines, device_values)
    env_text = build_env_text(lines)

    if args.dry_run:
        print(env_text, end="")
        summary_stream = sys.stderr
    else:
        args.env_file.parent.mkdir(parents=True, exist_ok=True)
        args.env_file.write_text(env_text)
        summary_stream = sys.stdout
        print(f"Wrote {args.env_file}", file=summary_stream)

    print(
        f"{DEVICE_ENV_KEYS[0]}={device_values[DEVICE_ENV_KEYS[0]]}",
        file=summary_stream,
    )
    print(
        f"{DEVICE_ENV_KEYS[1]}={device_values[DEVICE_ENV_KEYS[1]]}",
        file=summary_stream,
    )
    print(
        f"{DEVICE_ENV_KEYS[2]}={device_values[DEVICE_ENV_KEYS[2]]}",
        file=summary_stream,
    )
    if len(keyboard_paths) > len(args.order):
        extras = ", ".join(keyboard_paths[len(args.order) :])
        print(f"Ignored extra keyboard devices: {extras}", file=summary_stream)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
