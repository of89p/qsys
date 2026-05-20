# QSys Raspberry Pi Setup

Use this guide when preparing a Raspberry Pi from a fresh checkout of the QSys
source code.

## What You Need

- Raspberry Pi OS or another Linux system with systemd
- Python 3.12 or newer
- `curl` or `wget` for installing `uv`
- Network access from the TV/browser to the Pi
- One or two USB keyboard/keypad receivers
- The QSys source code copied or cloned onto the Pi

## 1. Get The Source

Copy or clone the project onto the Pi, then enter the project directory:

```bash
cd /path/to/qsys
```

If using git, this usually looks like:

```bash
git clone <repo-url> qsys
cd qsys
```

## 2. Install uv

Install `uv` with the official standalone installer from the
[uv installation docs](https://docs.astral.sh/uv/getting-started/installation/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If `curl` is not installed, use `wget`:

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```

The installer usually places `uv` in `~/.local/bin`. Start a new shell, or make
it available in the current shell:

```bash
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

## 3. Install Python Dependencies

Use `uv` from the project directory:

```bash
uv sync
```

Or use standard Python tooling:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

The service installer prefers `.venv/bin/python` when it exists.

## 4. Plug In Keypads

Plug in the food keypad, and the drinks keypad if used. Check that Linux can see
the input devices:

```bash
ls -l /dev/input/by-path/
```

The useful entries are the ones ending in `-event-kbd`.
`/dev/input/by-path` is used because it identifies the USB port path, which is
more useful than `/dev/input/by-id` when two keypads are the same brand.
If you prefer the old brand/device-id paths, pass
`--device-dir /dev/input/by-id` to `scripts/update_env_from_ls.py` or
`scripts/install_systemd_services.py`.
The setup scripts ignore `/dev/input/by-id/usb-Keychron_Keychron_K6-event-kbd`
because that keyboard is reserved as the dev keyboard. When scanning
`/dev/input/by-path`, the matching by-path symlink is ignored too.

## 5. Install Services

Run the installer from the project directory:

```bash
sudo python3 scripts/install_systemd_services.py
```

The installer:

- Detects this checkout path.
- Detects the Linux user that should run the services.
- Uses `.venv/bin/python` when available.
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
  --python /home/pi/qsys/.venv/bin/python
```

Preview the generated service files without changing the system:

```bash
python3 scripts/install_systemd_services.py --dry-run
```

## 6. Check The Display

Find the Pi IP address:

```bash
hostname -I
```

Open this URL from the TV or another browser on the same network:

```text
http://<pi-ip-address>:8080/
```

## 7. Test Without A Keypad

Submit a food queue number manually:

```bash
curl -X POST http://127.0.0.1:8080/api/queue \
  -H 'Content-Type: application/json' \
  -d '{"station":"food","number":"12"}'
```

The display should show `012`.

## Keypad Assignment

The generated `.env` stores keypad paths:

```env
FOOD_DEVICE_PATH=/dev/input/by-path/<food-keypad-event-kbd>
DRINKS_DEVICE_PATH=/dev/input/by-path/<drinks-keypad-event-kbd>
```

By default, the first detected `*-event-kbd` device becomes `FOOD_DEVICE_PATH`
and the second becomes `DRINKS_DEVICE_PATH`.
The generated paths normally begin with `/dev/input/by-path/`. Keep each keypad
plugged into the same USB port so those assignments stay stable.
The Keychron dev keyboard is excluded automatically and will not be assigned to
Food or Drinks.

If the keypads are reversed, regenerate `.env` with `--swap` and restart the
interceptor:

```bash
python3 scripts/update_env_from_ls.py --swap
sudo systemctl restart qsys-interceptor.service
```

If there is only one keypad, `DRINKS_DEVICE_PATH` stays empty.

## Service Commands

Check service status:

```bash
systemctl status qsys-server.service
systemctl status qsys-interceptor.service
```

View logs:

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
sudo python3 scripts/install_systemd_services.py
```

If you are not using `uv`, reinstall dependencies in the virtual environment:

```bash
. .venv/bin/activate
pip install -r requirements.txt
sudo python3 scripts/install_systemd_services.py
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
python3 scripts/update_env_from_ls.py
sudo systemctl restart qsys-interceptor.service
```

If the interceptor reports permission errors, rerun the installer or add the
service user to the `input` group:

```bash
sudo usermod -aG input "$USER"
sudo systemctl restart qsys-interceptor.service
```

If port `8080` is already in use, stop the other process or change the port in
`app/server.py`.

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
