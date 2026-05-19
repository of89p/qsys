# QSys Order Queue

QSys is a simple order collection display. A Flask server serves the TV page and keeps the current queue state in memory. An optional keyboard interceptor reads USB keypad input from `/dev/input` and sends completed order numbers to the server.

The display is available at:

```text
http://<pi-ip-address>:8080/
```

## Requirements

- Linux or Raspberry Pi OS
- Python 3.12 or newer
- USB keyboard/keypad receiver
- Network access from the TV/browser to the machine running the server

## Install

For Raspberry Pi deployment, use [SETUP.md](SETUP.md).

From the project directory:

```bash
cd /path/to/qsys
```

If you use `uv`:

```bash
uv sync
```

Or with standard Python tooling:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Run Manually

Start the web server in one terminal and keep it running:

```bash
.venv/bin/python app/server.py
```

Open the display from the same machine:

```text
http://127.0.0.1:8080/
```

From another device on the same network, find the machine IP address:

```bash
hostname -I
```

Then open:

```text
http://<pi-ip-address>:8080/
```

You can test the queue API without a keypad:

```bash
curl -X POST http://127.0.0.1:8080/api/queue \
  -H 'Content-Type: application/json' \
  -d '{"station":"food","number":"12"}'
```

The display page is read-only. Order numbers should be submitted through
`/api/queue`, either from the USB keypad interceptor or from a manual API call.
The display receives live updates from `/api/events` using server-sent events.
`/api/state` remains available as a snapshot endpoint for manual checks.

## Set Up USB Keypads

List connected input devices:

```bash
ls -l /dev/input/by-id/
```

Generate or update `.env` from the detected keyboard device paths:

```bash
python3 scripts/update_env_from_ls.py
```

If you saved the `ls -l /dev/input/by-id/` output to a file, pass it in:

```bash
python3 scripts/update_env_from_ls.py --from-file devlogs/ls-logs.txt
```

The first `*-event-kbd` device is written as `FOOD_DEVICE_PATH`; the second is
written as `DRINKS_DEVICE_PATH`. Add `--swap` if those two assignments should be
reversed.

Use the `*-event-kbd` path for each keypad. Example:

```text
/dev/input/by-id/usb-Logitech_USB_Receiver-if02-event-kbd
```

Run the interceptor with one keypad in a second terminal:

```bash
set -a
. ./.env
set +a
.venv/bin/python app/interceptor.py
```

If you have not added your user to the `input` group, run the same manual test
with `sudo`:

```bash
sudo env FOOD_DEVICE_PATH=/dev/input/by-id/usb-Logitech_USB_Receiver-if02-event-kbd \
  QSYS_QUEUE_URL=http://127.0.0.1:8080/api/queue \
  .venv/bin/python app/interceptor.py
```

Run it with separate food and drinks keypads:

```bash
FOOD_DEVICE_PATH=/dev/input/by-id/<food-keypad-event-kbd> \
DRINKS_DEVICE_PATH=/dev/input/by-id/<drinks-keypad-event-kbd> \
.venv/bin/python app/interceptor.py
```

The interceptor reads digits, accepts `Backspace`, and submits the number when `Enter` is pressed. Submitted numbers are padded to 3 digits on the display.
It reads the input device without an exclusive grab, so non-keypad input passes
through to the OS normally. By default it only treats keypad events such as
`KEY_KP1` and `KEY_KPENTER` as order input. If your keypad reports plain number
row keys instead, set `QSYS_ACCEPT_ROW_DIGITS=1`.

Access to `/dev/input` usually requires the `input` group:

```bash
sudo usermod -aG input "$USER"
```

Log out and back in after changing groups. For a quick manual test only, you can run the interceptor with `sudo`, but the systemd service below is configured to use the `input` group.

## Install As System Services

The service templates are in `systemd/`. Install them with the setup script from
the project directory:

```bash
sudo python3 scripts/install_systemd_services.py
```

The script detects this checkout path, the service user, and the Python
executable, then renders real `qsys-server.service` and
`qsys-interceptor.service` files into `/etc/systemd/system/`. It also updates
`.env` from `/dev/input/by-id`, adds the service user to the `input` group, runs
`systemctl daemon-reload`, enables both services, and restarts them.

For an image build or a nonstandard install, pass explicit values:

```bash
sudo python3 scripts/install_systemd_services.py \
  --user pi \
  --root /home/pi/qsys \
  --python /home/pi/qsys/.venv/bin/python
```

Preview without changing the system:

```bash
python3 scripts/install_systemd_services.py --dry-run
```

Check status:

```bash
systemctl status qsys-server.service
systemctl status qsys-interceptor.service
```

View logs for systemd services:

```bash
journalctl -u qsys-server.service -f
journalctl -u qsys-interceptor.service -f
```

When running manually, logs are printed directly in the terminal running
`app/server.py` or `app/interceptor.py`.

The interceptor logs keypad presses, unmapped keys, buffer changes, and queue
submissions.

Restart after making changes:

```bash
sudo systemctl restart qsys-server.service
sudo systemctl restart qsys-interceptor.service
```

## Configuration

The interceptor supports these environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `QSYS_QUEUE_URL` | `http://127.0.0.1:8080/api/queue` | Server endpoint that receives keypad submissions. |
| `QSYS_LOG_LEVEL` | `INFO` | Interceptor logging level. |
| `QSYS_ACCEPT_ROW_DIGITS` | empty | Set to `1` only if your keypad sends normal number-row keycodes instead of keypad keycodes. |
| `FOOD_DEVICE_PATH` | empty | Input device for the Food station. |
| `DRINKS_DEVICE_PATH` | empty | Input device for the Drinks and Snacks station. |

The server listens on `0.0.0.0:8080`.

## Troubleshooting

- If the TV cannot load the page, confirm the server is running and open `http://<pi-ip-address>:8080/` from a browser on the same network.
- If port `8080` is already in use, stop the other process or change the port in `app/server.py`.
- If the interceptor prints a permission error, add the service user to the `input` group and restart the login session or the service.
- If keypad input does nothing, re-run `ls -l /dev/input/by-id/` and confirm the service uses the correct `*-event-kbd` path.
- Queue state is stored in memory, so restarting the server clears the display.
