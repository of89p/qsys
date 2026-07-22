# QSys Raspberry Pi Setup

Use this guide when preparing a Raspberry Pi from a fresh checkout of the QSys
source code.

## What You Need

- Raspberry Pi OS or another Linux system with systemd
- Node.js 20.9 or newer
- pnpm
- Python 3.12 or newer
- `curl` or `wget` for installing `uv`
- Up to three USB keyboard/keypad receivers
- The QSys source code copied or cloned onto the Pi

## 0. Prepare The Pi

Plug in the Food, Drinks, and Chicken keypads, plus a dev keyboard if needed.

Connect to Wi-Fi:

```bash
nmcli device wifi list
nmcli device wifi connect "YOUR_SSID" password "YOUR_PASSWORD"
```

Update Linux and install Git:

```bash
sudo apt update
sudo apt install -y git
git --version
```

Install Node.js 20.9 or newer and enable pnpm with Corepack:

```bash
node --version
corepack enable
corepack prepare pnpm@latest --activate
pnpm --version
```

If `node --version` is older than 20.9, install a newer Node release before
continuing.

## 1. Get The Source

```bash
git clone https://github.com/of89p/qsys.git
cd qsys
```

## 2. Install Python Dependencies

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

Install the interceptor dependencies:

```bash
uv sync
```

If you are not using `uv`:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 3. Install And Build The Frontend

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
```

The build creates the standalone Next.js server used by `qsys-server.service`.

## 4. Plug In Keypads

Check that Linux can see the input devices:

```bash
ls -l /dev/input/by-path/
```

The useful entries are the ones ending in `-event-kbd`. `/dev/input/by-path`
is used because it identifies the USB port path, which is more stable when
multiple keypads are the same brand.

## 5. Install Services

Run the installer from the project directory:

```bash
sudo python3 scripts/install_systemd_services.py
```

The installer:

- Detects this checkout path.
- Detects the Linux user that should run the services.
- Uses `.venv/bin/python` when available.
- Detects `node` from `PATH`.
- Generates `.env` from `/dev/input/by-path`.
- Renders and installs the systemd services.
- Adds the service user to the `input` group.
- Enables and restarts both services.

The installed services are:

```text
qsys-server.service
qsys-interceptor.service
```

For a nonstandard install, pass explicit values:

```bash
sudo python3 scripts/install_systemd_services.py \
  --user pi \
  --root /home/pi/qsys \
  --python /home/pi/qsys/.venv/bin/python \
  --node /usr/bin/node
```

Preview the generated service files without changing the system:

```bash
python3 scripts/install_systemd_services.py --dry-run
```

## 6. Set Up The Pi Display Browser

Autostart Chromium in kiosk mode with a dedicated local profile and the autoplay
policy required for the notification sound:

```bash
mkdir -p ~/.config/qsys-chromium
mkdir -p ~/.config/labwc
nano ~/.config/labwc/autostart
```

Add this line:

```bash
chromium --kiosk --user-data-dir="$HOME/.config/qsys-chromium" --autoplay-policy=no-user-gesture-required --noerrdialogs --disable-infobars --no-first-run --start-maximized --force-device-scale-factor=1 http://127.0.0.1:8080/ &
```

If the command is named `chromium-browser` on your Pi, use that instead of
`chromium`.

If the display appears zoomed in or out, reset the dedicated kiosk profile once
and restart Chromium:

```bash
rm -rf ~/.config/qsys-chromium
mkdir -p ~/.config/qsys-chromium
```

The `--force-device-scale-factor=1` flag keeps Chromium at a 100% device scale.
If the page still appears incorrectly sized after resetting the profile, check
the Raspberry Pi OS display scaling settings.

## 7. Check The Display

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
python3 scripts/update_env_from_ls.py --order food,drinks,chicken
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

Restart after changing code or `.env`:

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

From the project directory:

```bash
git pull
uv sync
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
sudo python3 scripts/install_systemd_services.py
```

If you are not using `uv`, reinstall dependencies in the virtual environment
before rerunning the service installer.

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
python3 scripts/update_env_from_ls.py
sudo systemctl restart qsys-interceptor.service
```

If the interceptor reports permission errors, rerun the installer or add the
service user to the `input` group:

```bash
sudo usermod -aG input "$USER"
sudo systemctl restart qsys-interceptor.service
```

If port `8080` is already in use, stop the other process or change `PORT` in
the root `.env`.

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
