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

From the project directory:

```bash
cd /home/yy/nus/qsys
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

Start the web server:

```bash
.venv/bin/python server.py
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

The display also accepts direct keyboard input in the browser:

- Press `f` to select Food.
- Press `d` to select Drinks and Snacks.
- Type up to 3 digits.
- Press `Enter` to add the order number.
- Press `Backspace` to edit the current input.

## Set Up USB Keypads

List connected input devices:

```bash
ls -l /dev/input/by-id/
```

Use the `*-event-kbd` path for each keypad. Example:

```text
/dev/input/by-id/usb-Logitech_USB_Receiver-if02-event-kbd
```

Run the interceptor with one keypad:

```bash
FOOD_DEVICE_PATH=/dev/input/by-id/usb-Logitech_USB_Receiver-if02-event-kbd \
.venv/bin/python interceptor.py
```

Run it with separate food and drinks keypads:

```bash
FOOD_DEVICE_PATH=/dev/input/by-id/<food-keypad-event-kbd> \
DRINKS_DEVICE_PATH=/dev/input/by-id/<drinks-keypad-event-kbd> \
.venv/bin/python interceptor.py
```

The interceptor reads digits, accepts `Backspace`, and submits the number when `Enter` is pressed. Submitted numbers are padded to 3 digits on the display.

Access to `/dev/input` usually requires the `input` group:

```bash
sudo usermod -aG input "$USER"
```

Log out and back in after changing groups. For a quick manual test only, you can run the interceptor with `sudo`, but the systemd service below is configured to use the `input` group.

## Install As System Services

The service files are in `systemd/`:

- `systemd/qsys-server.service`
- `systemd/qsys-interceptor.service`

Before installing them, edit both files if needed:

- Set `User=` to the Linux user that owns this project.
- Set `WorkingDirectory=` to this project directory.
- Set `ExecStart=` to this project's `.venv/bin/python`.
- Set `FOOD_DEVICE_PATH=` and, if used, `DRINKS_DEVICE_PATH=` in `qsys-interceptor.service`.

Install and start the services:

```bash
sudo cp systemd/qsys-server.service /etc/systemd/system/
sudo cp systemd/qsys-interceptor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qsys-server.service
sudo systemctl enable --now qsys-interceptor.service
```

Check status:

```bash
systemctl status qsys-server.service
systemctl status qsys-interceptor.service
```

View logs:

```bash
journalctl -u qsys-server.service -f
journalctl -u qsys-interceptor.service -f
```

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
| `FOOD_DEVICE_PATH` | `/dev/input/by-id/usb-Logitech_USB_Receiver-if02-event-kbd` | Input device for the Food station. |
| `DRINKS_DEVICE_PATH` | empty | Input device for the Drinks and Snacks station. |

The server listens on `0.0.0.0:8080`.

## Troubleshooting

- If the TV cannot load the page, confirm the server is running and open `http://<pi-ip-address>:8080/` from a browser on the same network.
- If port `8080` is already in use, stop the other process or change the port in `server.py`.
- If the interceptor prints a permission error, add the service user to the `input` group and restart the login session or the service.
- If keypad input does nothing, re-run `ls -l /dev/input/by-id/` and confirm the service uses the correct `*-event-kbd` path.
- Queue state is stored in memory, so restarting the server clears the display.
