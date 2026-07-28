#!/bin/sh
# Remove QSys systemd services and kiosk autostart entries.
set -eu

SERVICE_NAMES="qsys-interceptor.service qsys-server.service"
DEFAULT_INSTALL_DIR=/etc/systemd/system
DEFAULT_KIOSK_AUTOSTART_FILE=.config/autostart/qsys-kiosk.desktop
LEGACY_AUTOSTART_FILE=.config/labwc/autostart
LEGACY_AUTOSTART_BEGIN="# >>> QSys Chromium kiosk >>>"
LEGACY_AUTOSTART_END="# <<< QSys Chromium kiosk <<<"

INSTALL_DIR=$DEFAULT_INSTALL_DIR
AUTOSTART_FILE=
SERVICE_USER=${QSYS_USER:-${SUDO_USER:-}}
SKIP_SYSTEMD=0
SKIP_KIOSK_AUTOSTART=0
DRY_RUN=0

usage() {
    cat <<'EOF'
Usage: ./uninstall.sh [options]

Options:
  --user USER                User that owns the kiosk autostart file.
                             Default: QSYS_USER, SUDO_USER, then current user.
  --install-dir DIR          systemd unit directory. Default: /etc/systemd/system.
  --autostart-file FILE      Kiosk autostart file to remove.
                             Default: ~USER/.config/autostart/qsys-kiosk.desktop.
  --skip-systemd             Do not stop, disable, or remove systemd services.
  --skip-kiosk-autostart     Do not remove kiosk autostart entries.
  --dry-run                  Print actions without changing files or services.
  -h, --help                 Show this help.
EOF
}

parse_args() {
    expected=
    for arg in "$@"; do
        if [ -n "$expected" ]; then
            case "$expected" in
                user)
                    SERVICE_USER=$arg
                    ;;
                install_dir)
                    INSTALL_DIR=$arg
                    ;;
                autostart_file)
                    AUTOSTART_FILE=$arg
                    ;;
            esac
            expected=
            continue
        fi

        case "$arg" in
            --user)
                expected=user
                ;;
            --user=*)
                SERVICE_USER=${arg#--user=}
                ;;
            --install-dir)
                expected=install_dir
                ;;
            --install-dir=*)
                INSTALL_DIR=${arg#--install-dir=}
                ;;
            --autostart-file)
                expected=autostart_file
                ;;
            --autostart-file=*)
                AUTOSTART_FILE=${arg#--autostart-file=}
                ;;
            --skip-systemd)
                SKIP_SYSTEMD=1
                ;;
            --skip-kiosk-autostart)
                SKIP_KIOSK_AUTOSTART=1
                ;;
            --dry-run)
                DRY_RUN=1
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Uninstall failed: unknown option: $arg" >&2
                usage >&2
                exit 1
                ;;
        esac
    done

    if [ -n "$expected" ]; then
        echo "Uninstall failed: missing value for --$expected" >&2
        exit 1
    fi
}

run() {
    echo "+ $*"
    if [ "$DRY_RUN" -eq 0 ]; then
        "$@"
    fi
}

run_optional() {
    echo "+ $*"
    if [ "$DRY_RUN" -eq 0 ]; then
        "$@" || true
    fi
}

remove_file() {
    path=$1
    label=$2

    if [ ! -e "$path" ] && [ ! -L "$path" ]; then
        echo "Already removed: $path"
        return
    fi

    echo "Removing $label: $path"
    run rm -f "$path"
}

remove_legacy_autostart_block() {
    path=$1

    if [ ! -f "$path" ]; then
        return
    fi

    if ! grep -F "$LEGACY_AUTOSTART_BEGIN" "$path" >/dev/null 2>&1; then
        return
    fi
    if ! grep -F "$LEGACY_AUTOSTART_END" "$path" >/dev/null 2>&1; then
        return
    fi

    echo "Removing legacy QSys kiosk block from: $path"
    if [ "$DRY_RUN" -eq 1 ]; then
        return
    fi

    tmp=$(mktemp "${TMPDIR:-/tmp}/qsys-autostart.XXXXXX")
    awk -v begin="$LEGACY_AUTOSTART_BEGIN" -v end="$LEGACY_AUTOSTART_END" '
        $0 == begin { skip = 1; next }
        $0 == end { skip = 0; next }
        !skip { print }
    ' "$path" > "$tmp"
    cp "$tmp" "$path"
    rm -f "$tmp"

    if [ ! -s "$path" ]; then
        rm -f "$path"
    fi
}

uninstall_systemd() {
    if command -v systemctl >/dev/null 2>&1; then
        run_optional systemctl disable --now $SERVICE_NAMES
    else
        echo "Warning: systemctl not found; only removing unit files." >&2
    fi

    for service_name in $SERVICE_NAMES; do
        remove_file "$INSTALL_DIR/$service_name" "systemd unit"
    done

    if command -v systemctl >/dev/null 2>&1; then
        run systemctl daemon-reload
        run_optional systemctl reset-failed $SERVICE_NAMES
    fi
}

uninstall_kiosk_autostart() {
    if [ -z "$SERVICE_USER" ] || [ "$SERVICE_USER" = "root" ]; then
        echo "Uninstall failed: could not infer kiosk user. Pass --user <linux-user>." >&2
        exit 1
    fi

    service_home=$(getent passwd "$SERVICE_USER" | cut -d: -f6)
    if [ -z "$service_home" ]; then
        echo "Uninstall failed: could not find home directory for $SERVICE_USER." >&2
        exit 1
    fi

    if [ -z "$AUTOSTART_FILE" ]; then
        AUTOSTART_FILE=$service_home/$DEFAULT_KIOSK_AUTOSTART_FILE
    fi

    remove_file "$AUTOSTART_FILE" "kiosk autostart"
    remove_legacy_autostart_block "$service_home/$LEGACY_AUTOSTART_FILE"
}

parse_args "$@"

if [ -z "$SERVICE_USER" ] && [ "$(id -u)" -ne 0 ]; then
    SERVICE_USER=$(id -un)
fi

if [ "$SKIP_SYSTEMD" -eq 0 ] && [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    exec sudo env QSYS_USER="$SERVICE_USER" sh "$0" "$@"
fi

if [ "$SKIP_SYSTEMD" -eq 0 ]; then
    uninstall_systemd
fi

if [ "$SKIP_KIOSK_AUTOSTART" -eq 0 ]; then
    uninstall_kiosk_autostart
fi

echo "QSys uninstall complete."
