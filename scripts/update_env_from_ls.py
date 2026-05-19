#!/usr/bin/env python3
"""Update .env keypad paths from `ls -l /dev/input/by-id/` output."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICE_DIR = Path("/dev/input/by-id")

DEFAULT_ENV_VALUES = {
    "PYTHONUNBUFFERED": "1",
    "QSYS_LOG_LEVEL": "INFO",
    "QSYS_QUEUE_URL": "http://127.0.0.1:8080/api/queue",
    "QSYS_ACCEPT_ROW_DIGITS": "0",
    "FOOD_DEVICE_PATH": "",
    "DRINKS_DEVICE_PATH": "",
}

DEVICE_ENV_KEYS = ("FOOD_DEVICE_PATH", "DRINKS_DEVICE_PATH")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find *-event-kbd devices in ls output and write FOOD_DEVICE_PATH "
            "and DRINKS_DEVICE_PATH into .env."
        )
    )
    parser.add_argument(
        "--device-dir",
        type=Path,
        default=DEFAULT_DEVICE_DIR,
        help="Input device directory to list. Default: /dev/input/by-id",
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
        help="Read saved output from `ls -l /dev/input/by-id/` instead of running ls.",
    )
    source.add_argument(
        "--stdin",
        action="store_true",
        help="Read `ls -l /dev/input/by-id/` output from standard input.",
    )
    parser.add_argument(
        "--swap",
        action="store_true",
        help="Swap the first two detected keyboard devices before writing .env.",
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


def parse_keyboard_paths(ls_output: str, device_dir: Path) -> list[str]:
    paths: list[str] = []

    for raw_line in ls_output.splitlines():
        if " -> " not in raw_line:
            continue

        before_arrow = raw_line.split(" -> ", 1)[0].strip()
        if not before_arrow:
            continue

        link_name = before_arrow.split()[-1]
        if not link_name.endswith("-event-kbd"):
            continue

        link_path = Path(link_name)
        if not link_path.is_absolute():
            link_path = device_dir / link_path

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


def has_key(lines: list[str], key: str) -> bool:
    return any(env_key(line) == key for line in lines)


def append_missing_defaults(lines: list[str]) -> list[str]:
    missing = [
        (key, value)
        for key, value in DEFAULT_ENV_VALUES.items()
        if not has_key(lines, key)
    ]
    if not missing:
        return lines

    updated = list(lines)
    if updated and updated[-1].strip():
        updated.append("")
    for key, value in missing:
        updated.append(f"{key}={value}")
    return updated


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
            "No *-event-kbd devices found. Run `ls -l /dev/input/by-id/` "
            "and confirm the keypad is connected.",
            file=sys.stderr,
        )
        return 1

    device_values = {
        DEVICE_ENV_KEYS[0]: keyboard_paths[0],
        DEVICE_ENV_KEYS[1]: keyboard_paths[1] if len(keyboard_paths) > 1 else "",
    }

    lines = load_env_lines(args.env_file, args.example_file)
    lines = append_missing_defaults(lines)
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
    if len(keyboard_paths) > len(DEVICE_ENV_KEYS):
        extras = ", ".join(keyboard_paths[len(DEVICE_ENV_KEYS) :])
        print(f"Ignored extra keyboard devices: {extras}", file=summary_stream)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
