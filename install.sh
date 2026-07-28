#!/bin/sh
# QSys Pi bootstrap flow:
# 1. Re-exec through sudo when started by the target service user.
# 2. Resolve the service user from --user, QSYS_USER, or SUDO_USER.
# 3. Install Python/runtime build prerequisites when apt-get is available.
# 4. Validate system Python 3.11+ and Node.js 20.9+.
# 5. Install or locate uv, then create/update .venv as the service user.
# 6. Delegate all QSys-specific setup to scripts/install.py.
set -eu

if [ "$(id -u)" -ne 0 ]; then
    if [ -n "${QSYS_USER:-}" ]; then
        exec sudo env QSYS_USER="$QSYS_USER" sh "$0" "$@"
    fi
    exec sudo sh "$0" "$@"
fi

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT_DIR"

user_from_args() {
    next_is_user=0
    for arg in "$@"; do
        if [ "$next_is_user" -eq 1 ]; then
            printf '%s\n' "$arg"
            return
        fi

        case "$arg" in
            --)
                return 0
                ;;
            --user)
                next_is_user=1
                ;;
            --user=*)
                printf '%s\n' "${arg#--user=}"
                return
                ;;
        esac
    done

    return 0
}

node_from_args() {
    next_is_node=0
    for arg in "$@"; do
        if [ "$next_is_node" -eq 1 ]; then
            printf '%s\n' "$arg"
            return
        fi

        case "$arg" in
            --)
                return 0
                ;;
            --node)
                next_is_node=1
                ;;
            --node=*)
                printf '%s\n' "${arg#--node=}"
                return
                ;;
        esac
    done

    return 0
}

SERVICE_USER=${QSYS_USER:-${SUDO_USER:-}}
ARG_USER=$(user_from_args "$@")
if [ -n "$ARG_USER" ]; then
    SERVICE_USER=$ARG_USER
fi

if [ -z "$SERVICE_USER" ] || [ "$SERVICE_USER" = "root" ]; then
    echo "Install failed: set QSYS_USER or run through sudo from the target user." >&2
    exit 1
fi

SERVICE_HOME=$(getent passwd "$SERVICE_USER" | cut -d: -f6)
if [ -z "$SERVICE_HOME" ]; then
    echo "Install failed: could not find home directory for $SERVICE_USER." >&2
    exit 1
fi

as_service_user() {
    if command -v sudo >/dev/null 2>&1; then
        sudo -H -u "$SERVICE_USER" "$@"
    elif command -v runuser >/dev/null 2>&1; then
        runuser -u "$SERVICE_USER" -- "$@"
    else
        echo "Install failed: sudo or runuser is required." >&2
        exit 1
    fi
}

node_from_service_user_nvm() {
    as_service_user sh -c '
        if [ -z "${NVM_DIR:-}" ]; then
            if [ -z "${XDG_CONFIG_HOME:-}" ]; then
                NVM_DIR="$HOME/.nvm"
            else
                NVM_DIR="$XDG_CONFIG_HOME/nvm"
            fi
        fi
        export NVM_DIR

        if [ -s "$NVM_DIR/nvm.sh" ]; then
            . "$NVM_DIR/nvm.sh"
            if command -v node >/dev/null 2>&1; then
                command -v node
                exit 0
            fi
            if nvm use --silent default >/dev/null 2>&1; then
                command -v node
                exit 0
            fi
            if nvm use --silent --lts >/dev/null 2>&1; then
                command -v node
                exit 0
            fi
        fi

        exit 1
    '
}

if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y \
        build-essential \
        ca-certificates \
        curl \
        python3 \
        python3-dev \
        python3-venv
else
    echo "Warning: apt-get not found; skipping OS package installation." >&2
fi

if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    echo "Install failed: Python 3.11 or newer is required. Found $(python3 --version)." >&2
    exit 1
fi

ARG_NODE=$(node_from_args "$@")
if [ -n "$ARG_NODE" ]; then
    NODE_BIN=$ARG_NODE
elif command -v node >/dev/null 2>&1; then
    NODE_BIN=$(command -v node)
else
    NODE_BIN=$(node_from_service_user_nvm || true)
fi

if [ -z "$NODE_BIN" ]; then
    echo "Install failed: Node.js 20.9 or newer must be installed before QSys." >&2
    exit 1
fi

if [ ! -x "$NODE_BIN" ]; then
    echo "Install failed: Node executable does not exist or is not executable: $NODE_BIN" >&2
    exit 1
fi

if ! "$NODE_BIN" -e "const [major, minor] = process.versions.node.split('.').map(Number); process.exit(major > 20 || (major === 20 && minor >= 9) ? 0 : 1);"; then
    echo "Install failed: Node.js 20.9 or newer is required. Found $("$NODE_BIN" --version)." >&2
    exit 1
fi

UV_BIN="$SERVICE_HOME/.local/bin/uv"
if [ ! -x "$UV_BIN" ]; then
    if command -v uv >/dev/null 2>&1; then
        UV_BIN=$(command -v uv)
    else
        as_service_user sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
        if [ ! -x "$UV_BIN" ]; then
            echo "Install failed: uv installation did not create $UV_BIN." >&2
            exit 1
        fi
    fi
fi

as_service_user "$UV_BIN" sync --frozen --no-dev --python python3 --no-python-downloads

PYTHON="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "Install failed: expected uv to create $PYTHON." >&2
    exit 1
fi

"$PYTHON" "$ROOT_DIR/scripts/install.py" --user "$SERVICE_USER" "$@" --node "$NODE_BIN"
