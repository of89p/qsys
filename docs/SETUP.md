# QSys Raspberry Pi Setup

Use this guide when preparing a Raspberry Pi from a QSys release artifact.

## What You Need

- Raspberry Pi OS or another Linux system with systemd
- Python 3.11 or newer from the OS package manager
- `bash` and `curl` for installing `nvm`, `uv`, and release artifacts
- Up to three USB keyboard/keypad receivers
- A QSys release tarball from CI or GitHub Releases

## 0. Prepare The Pi

Plug in the Food, Drinks, and Chicken keypads, plus a dev keyboard if needed.

Connect to Wi-Fi:

```bash
nmcli device wifi list
nmcli device wifi connect "YOUR_SSID" password "YOUR_PASSWORD"
```

Update Linux and install basic download tools:

```bash
sudo apt update
sudo apt install -y bash ca-certificates curl
```

The bootstrap installs Node.js LTS with `nvm` if Node.js 20.9 or newer is not
already available.

## 1. Download The Release

```bash
mkdir -p ~/qsys
cd ~/qsys
curl -L -o qsys-release.tar.gz <release-artifact-url>
tar -xzf qsys-release.tar.gz --strip-components=1
```

The release artifact includes the built Next.js server and the setup scripts.
It does not include `.env`, Git history, or frontend build tooling.

If you want to install Node.js before running the full bootstrap, use:

```bash
./scripts/install_node_nvm.sh
```

The full bootstrap runs the same helper automatically when needed. The helper
installs `nvm` for the service user, runs `nvm install --lts`, and sets the LTS
line as the default Node.js version. The production Pi does not need `pnpm`
because it does not build the frontend locally.

## 2. Plug In Keypads

Check that Linux can see the input devices:

```bash
ls -l /dev/input/by-path/
```

The useful entries are the ones ending in `-event-kbd`. `/dev/input/by-path`
is used because it identifies the USB port path, which is more stable when
multiple keypads are the same brand.

## 3. Install Services

Run the bootstrap from the extracted release directory:

```bash
./install.sh
```

The bootstrap and installer:

- Detects the extracted release path.
- Detects the Linux user that should run the services.
- Installs Python runtime and build prerequisites when `apt-get` is available.
- Installs or detects `uv`.
- Creates `.venv` with runtime Python dependencies.
- Installs Node.js LTS with `nvm` when Node.js 20.9 or newer is not available.
- Overwrites `.env` from `.env.example` and detected `/dev/input/by-path` keypads.
- Configures Chromium kiosk autostart idempotently.
- Uses `.venv/bin/python` when available.
- Detects `node` from `--node`, `PATH`, or the service user's `nvm` install.
- Renders and installs systemd services, including interceptor startup `.env`
  regeneration.
- Adds the service user to the `input` group.
- Enables and restarts both services.

The installed services are:

```text
qsys-server.service
qsys-interceptor.service
```

For a nonstandard install, pass explicit values:

```bash
./install.sh \
  --user pi \
  --chromium-command chromium-browser \
  --python /home/pi/qsys/.venv/bin/python \
  --node /usr/bin/node
```

Use `scripts/install.py --systemd-only` when you only want to update systemd
services and leave Chromium autostart untouched. Add `--no-start` if you also
want to avoid the interceptor startup `.env` refresh during the install run.

Preview the generated service files without changing the system:

```bash
python3 scripts/install.py --dry-run
```

## 4. Set Up The Pi Display Browser

`scripts/install.py` writes a managed QSys block into
`~/.config/labwc/autostart`. Re-running the installer replaces that block
without duplicating it or changing unrelated autostart entries. The Chromium
command uses a dedicated local profile, enables notification sound autoplay,
starts at `http://127.0.0.1:8080/`, and forces 100% device scale.

If the command is named `chromium-browser` on your Pi, rerun the installer with:

```bash
./install.sh --chromium-command chromium-browser
```

If the display appears zoomed in or out, reset the dedicated kiosk profile once
and restart Chromium:

```bash
rm -rf ~/.config/qsys-chromium
mkdir -p ~/.config/qsys-chromium
```

The `--force-device-scale-factor=1` flag keeps Chromium at a 100% device scale.
If the page still appears incorrectly sized after resetting the profile, check
the Raspberry Pi OS display scaling settings.

## 5. Check The Display

Find the Pi IP address:

```bash
hostname -I
```

Open this URL from the TV or another browser on the same network:

```text
http://<pi-ip-address>:8080/
```

Submit a food queue number manually:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/queue \
  -H 'Content-Type: application/json' \
  -d '{"station":"food","number":"12"}'
```

The display should show `012`.

## Keypad Assignment

The generated `.env` stores keypad paths:

```env
FOOD_DEVICE_PATH=/dev/input/by-path/<food-keypad-event-kbd>
DRINKS_DEVICE_PATH=/dev/input/by-path/<drinks-keypad-event-kbd>
CHICKEN_DEVICE_PATH=/dev/input/by-path/<chicken-keypad-event-kbd>
```

By default, the first detected `*-event-kbd` device becomes `FOOD_DEVICE_PATH`,
the second becomes `DRINKS_DEVICE_PATH`, and the third becomes
`CHICKEN_DEVICE_PATH`. Use an explicit assignment order when needed:

```bash
python3 scripts/update_keypad_env.py --order food,drinks,chicken
sudo systemctl restart qsys-interceptor.service
```

Use `--device-dir /dev/input/by-id` if you prefer device-id paths. Use `--swap`
for older two-keypad Food/Drinks setups.

## Service Commands

Check service status:

```bash
systemctl status qsys-server.service
systemctl status qsys-interceptor.service
```

View logs from journald:

```bash
journalctl -u qsys-server.service -f
journalctl -u qsys-interceptor.service -f
```

Restart after changing code or `.env`. Starting the interceptor refreshes keypad
paths in `.env`, so rebooting the Pi is enough after hot swapping USB receivers:

```bash
sudo systemctl restart qsys-server.service
sudo systemctl restart qsys-interceptor.service
```

Stop services:

```bash
sudo systemctl stop qsys-interceptor.service
sudo systemctl stop qsys-server.service
```

## Updating A Pi

From the extracted release directory:

```bash
cd ~/qsys
curl -L -o qsys-release.tar.gz <release-artifact-url>
tar -xzf qsys-release.tar.gz --strip-components=1
./install.sh
```

The installer overwrites `.env` from `.env.example` on each run, then writes the
currently detected keypad paths. The installed interceptor service repeats that
refresh before every interceptor start.

## Development Or Fallback Source Install

Use a source checkout only for development, direct debugging, or emergency
fallback when no release artifact is available:

```bash
git clone https://github.com/of89p/qsys.git
cd qsys
uv sync
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
sudo python3 scripts/install.py
```

You can also ask the installer to build the frontend explicitly:

```bash
sudo python3 scripts/install.py --build-frontend
```

## Troubleshooting

If the TV cannot load the page, confirm the server is running:

```bash
systemctl status qsys-server.service
```

If keypad input does nothing, check the interceptor logs:

```bash
journalctl -u qsys-interceptor.service -f
```

Then confirm `.env` points at current keyboard devices:

```bash
cat .env
ls -l /dev/input/by-path/
```

Regenerate `.env` after changing USB receivers:

```bash
python3 scripts/update_keypad_env.py
sudo systemctl restart qsys-interceptor.service
```

The installed `qsys-interceptor.service` runs the same `.env` regeneration
before every interceptor start, so rebooting the Pi also refreshes keypad paths
after USB receivers are swapped.

If the interceptor reports permission errors, rerun the installer or add the
service user to the `input` group:

```bash
sudo usermod -aG input "$USER"
sudo systemctl restart qsys-interceptor.service
```

If port `8080` is already in use, stop the other process or change `PORT` in
`.env.example`, then rerun the installer.

## Uninstall Services

Disable and stop both services:

```bash
sudo systemctl disable --now qsys-interceptor.service
sudo systemctl disable --now qsys-server.service
```

Remove the installed unit files:

```bash
sudo rm /etc/systemd/system/qsys-interceptor.service
sudo rm /etc/systemd/system/qsys-server.service
sudo systemctl daemon-reload
```
