# QSys Order Queue

QSys is a local order collection display for a Raspberry Pi kiosk. A production
Next.js server renders the TV display and exposes the queue API. A Python
keyboard interceptor reads USB keypad input from `/dev/input` and submits
completed order numbers to the server.

The display is available at:

```text
http://<pi-ip-address>:8080/
```

## Requirements

- Linux or Raspberry Pi OS
- Node.js 20.9 or newer
- Python 3.11 or newer
- Up to three USB keyboard/keypad receivers
- Network access from the TV/browser to the machine running the server

## Install

For Raspberry Pi deployment, use [docs/SETUP.md](docs/SETUP.md). The Pi
production path uses a release artifact and does not require `git clone`,
`pnpm install`, or `pnpm build`.

From a release artifact on the Pi:

```bash
mkdir -p ~/qsys
cd ~/qsys
curl -L -o qsys-release.tar.gz <release-artifact-url>
tar -xzf qsys-release.tar.gz --strip-components=1
./install.sh
```

For development from a source checkout:

```bash
cd /path/to/qsys
uv sync
cd frontend
pnpm install --frozen-lockfile
pnpm build
```

If you are not using `uv`:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Run Manually

Start the web server in one terminal:

```bash
cd frontend
pnpm build
pnpm start
```

Open the display:

```text
http://127.0.0.1:8080/
```

In another terminal, run the interceptor after configuring `.env`:

```bash
.venv/bin/python -m interceptor
```

You can test the queue API without a keypad:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/queue \
  -H 'Content-Type: application/json' \
  -d '{"station":"food","number":"12"}'
```

The display page is read-only. Order numbers should be submitted through
`/api/v1/queue`, either from the USB keypad interceptor or from a manual API
call. The display receives live updates from `/api/v1/events` using
server-sent events. `/api/v1/state` is available as a diagnostic snapshot
endpoint.

## API Contract

`POST /api/v1/queue` accepts:

```json
{"station":"food","number":"12"}
```

`station` must be `drinks`, `chicken`, or `food`. `number` must contain digits
only and be at most 3 digits. Successful responses include the current state:

```json
{
  "ok": true,
  "state": {
    "version": 1,
    "queues": {
      "drinks": [],
      "chicken": [],
      "food": [
        {"callId": 1, "number": "012", "calledAt": "2026-07-23T10:12:30.000Z"}
      ]
    },
    "latestCall": {
      "callId": 1,
      "station": "food",
      "number": "012",
      "calledAt": "2026-07-23T10:12:30.000Z"
    }
  }
}
```

Errors return `400`:

```json
{"ok":false,"error":"number must contain digits only"}
```

## Set Up USB Keypads

List connected input devices:

```bash
ls -l /dev/input/by-path/
```

Generate or update `.env` from the detected keyboard device paths:

```bash
python3 scripts/update_keypad_env.py
```

The first `*-event-kbd` device is written as `FOOD_DEVICE_PATH`; the second is
written as `DRINKS_DEVICE_PATH`; the third is written as
`CHICKEN_DEVICE_PATH`. Use `--order food,drinks,chicken` to make the assignment
explicit, or pass a different station order to match the `ls` output. Add
`--swap` for older two-keypad Food/Drinks setups.

The default `/dev/input/by-path` paths are tied to USB ports. Keep each keypad
in the same USB port after setup. The generator skips the configured dev
keyboards so they are not assigned to a station.

## Install As System Services

The service templates are in `systemd/`. From a release artifact, install the
kiosk autostart and services with:

```bash
./install.sh
```

The bootstrap installs Python runtime/build prerequisites, creates `.venv`, then
delegates to `scripts/install.py`. The installer updates keypad paths in
`.env`, configures Chromium autostart for the Pi display from the generated
`PORT`, detects the release root, service user, Python, Node, and `.env`, then
renders and installs:

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

For a source checkout fallback, build the frontend before installing or run:

```bash
sudo python3 scripts/install.py --build-frontend
```

Preview without changing the system:

```bash
python3 scripts/install.py --dry-run
```

## Configuration

The root `.env` file is generated from `.env.example` whenever the installer or
`scripts/update_keypad_env.py` runs, and before `qsys-interceptor.service`
starts. Defaults are listed explicitly in `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NODE_ENV` | `production` | Runs the Next server in production mode. |
| `NEXT_TELEMETRY_DISABLED` | `1` | Disables Next telemetry. |
| `HOSTNAME` | `0.0.0.0` | Host bound by the standalone Next server. |
| `PORT` | `8080` | Port used by the display and API. |
| `NODE_OPTIONS` | `--max-old-space-size=128` | Caps V8 old-space heap growth. |
| `PYTHONUNBUFFERED` | `1` | Flushes Python logs promptly under systemd. |
| `QSYS_LOG_LEVEL` | `WARNING` | Python interceptor logging level. |
| `QSYS_QUEUE_URL` | `http://127.0.0.1:8080/api/v1/queue` | Interceptor queue endpoint. |
| `QSYS_ACCEPT_ROW_DIGITS` | `0` | Set to `1` if a keypad sends number-row keycodes. |
| `QSYS_MAX_VISIBLE_ORDERS` | `3` | Visible calls retained per station. |
| `QSYS_FLASH_DURATION_MS` | `10000` | Per-call flashing duration on the display. |
| `QSYS_SSE_HEARTBEAT_MS` | `15000` | SSE heartbeat interval. |
| `QSYS_AUTO_RELOAD_INTERVAL_MS` | `300000` | Kiosk page reload interval. |
| `FOOD_DEVICE_PATH` | empty | Input device for the Food station. |
| `DRINKS_DEVICE_PATH` | empty | Input device for the Drinks station. |
| `CHICKEN_DEVICE_PATH` | empty | Input device for the Chicken Rice station. |

## Service Commands

Check status:

```bash
systemctl status qsys-server.service
systemctl status qsys-interceptor.service
```

View logs from journald:

```bash
journalctl -u qsys-server.service -f
journalctl -u qsys-interceptor.service -f
```

Restart after changing code or `.env`. Starting the interceptor also refreshes
the keypad paths in `.env`, so rebooting the Pi is enough after hot swapping USB
receivers:

```bash
sudo systemctl restart qsys-server.service
sudo systemctl restart qsys-interceptor.service
```

Queue state is stored in memory, so restarting the server clears the display.

## Troubleshooting

- If the TV cannot load the page, confirm `qsys-server.service` is running and
  open `http://<pi-ip-address>:8080/` from a browser on the same network.
- If port `8080` is already in use, stop the other process or change `PORT` in
  `.env.example`, then rerun the installer.
- If the interceptor reports permission errors, add the service user to the
  `input` group and restart the login session or service.
- If keypad input does nothing, restart `qsys-interceptor.service` or reboot so
  startup refreshes `.env` from the currently detected receivers.
