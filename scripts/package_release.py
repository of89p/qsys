#!/usr/bin/env python3
"""Package a QSys release artifact from a checked and built source tree."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST_DIR = REPO_ROOT / "dist"

REQUIRED_PATHS = (
    ".env.example",
    ".python-version",
    "install.sh",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "frontend/.next/standalone/server.js",
)

PACKAGE_PATHS = (
    ".env.example",
    ".python-version",
    "install.sh",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "README.md",
    "docs",
    "interceptor",
    "scripts",
    "systemd",
    "frontend/.next/standalone",
    "frontend/.next/static",
    "frontend/public",
    "frontend/scripts",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create qsys-release-<version>.tar.gz from a built checkout."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="QSys checkout directory. Default: this repository.",
    )
    parser.add_argument(
        "--version",
        help="Version string used for the archive root directory and filename.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output .tar.gz path. Default: dist/qsys-release-<version>.tar.gz.",
    )
    return parser.parse_args()


def git_short_sha(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    return result.stdout.strip() or None


def release_version(root: Path, explicit_version: str | None) -> str:
    version = explicit_version or os.environ.get("QSYS_RELEASE_VERSION")
    version = version or os.environ.get("GITHUB_SHA", "")[:12]
    version = version or git_short_sha(root)
    return version or "local"


def safe_archive_name(version: str) -> str:
    safe_version = re.sub(r"[^A-Za-z0-9._-]+", "-", version).strip(".-")
    return f"qsys-release-{safe_version or 'local'}"


def require_paths(root: Path) -> None:
    missing = [path for path in REQUIRED_PATHS if not (root / path).exists()]
    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise RuntimeError(
            f"Cannot package release; missing required paths:\n{formatted}"
        )


def tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    path = PurePosixPath(info.name)
    if "__pycache__" in path.parts:
        return None
    if path.name.endswith((".pyc", ".pyo")):
        return None
    if path.name in {".DS_Store", ".env"}:
        return None

    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def create_archive(root: Path, output: Path, archive_root: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for relative_path in PACKAGE_PATHS:
            source = root / relative_path
            if not source.exists():
                continue
            archive.add(
                source,
                arcname=str(PurePosixPath(archive_root, relative_path)),
                filter=tar_filter,
            )


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    version = release_version(root, args.version)
    archive_root = safe_archive_name(version)
    output = (
        args.output.expanduser().resolve()
        if args.output
        else DEFAULT_DIST_DIR / f"{archive_root}.tar.gz"
    )

    try:
        require_paths(root)
        create_archive(root, output, archive_root)
    except RuntimeError as exc:
        print(f"Package failed: {exc}", file=sys.stderr)
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
