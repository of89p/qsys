#!/bin/sh
# Install nvm and Node.js for the QSys service user.
set -eu

NVM_VERSION=${NVM_VERSION:-v0.40.6}
if [ -z "${NODE_VERSION:-}" ]; then
    NODE_VERSION=--lts
fi

if [ "$(id -u)" -eq 0 ]; then
    TARGET_USER=${QSYS_USER:-${SUDO_USER:-}}
    if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
        echo "Install failed: run as the target service user, or set QSYS_USER." >&2
        exit 1
    fi

    if command -v sudo >/dev/null 2>&1; then
        exec sudo -H -u "$TARGET_USER" env \
            NODE_VERSION="$NODE_VERSION" \
            NVM_VERSION="$NVM_VERSION" \
            sh "$0" "$@"
    fi

    if command -v runuser >/dev/null 2>&1; then
        exec runuser -u "$TARGET_USER" -- env \
            NODE_VERSION="$NODE_VERSION" \
            NVM_VERSION="$NVM_VERSION" \
            sh "$0" "$@"
    fi

    echo "Install failed: sudo or runuser is required." >&2
    exit 1
fi

if ! command -v bash >/dev/null 2>&1; then
    echo "Install failed: bash is required to install nvm." >&2
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "Install failed: curl is required to install nvm." >&2
    exit 1
fi

if [ -z "${NVM_DIR:-}" ]; then
    if [ -z "${XDG_CONFIG_HOME:-}" ]; then
        NVM_DIR="$HOME/.nvm"
    else
        NVM_DIR="$XDG_CONFIG_HOME/nvm"
    fi
fi
export NVM_DIR

curl -o- "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" | bash

if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    echo "Install failed: nvm installation did not create $NVM_DIR/nvm.sh." >&2
    exit 1
fi

. "$NVM_DIR/nvm.sh"

nvm install "$NODE_VERSION"
if [ "$NODE_VERSION" = "--lts" ]; then
    nvm alias default "lts/*"
    nvm use --lts
else
    nvm alias default "$NODE_VERSION"
    nvm use "$NODE_VERSION"
fi

printf 'Installed Node.js %s\n' "$(node --version)"
printf 'Node executable: %s\n' "$(command -v node)"
