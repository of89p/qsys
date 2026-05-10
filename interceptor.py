import evdev
import asyncio
import os
import requests

API_URL = os.getenv("QSYS_QUEUE_URL", "http://127.0.0.1:8080/api/queue")
RETRY_SECONDS = 5
MAX_DIGITS = 3

# Set these from the systemd service. For now, ls-logs.txt shows one attached
# keyboard receiver, so the default assigns it to the food station.
DRINKS_DEVICE_PATH = os.getenv("DRINKS_DEVICE_PATH", "").strip()
FOOD_DEVICE_PATH = os.getenv(
    "FOOD_DEVICE_PATH",
    "/dev/input/by-id/usb-Logitech_USB_Receiver-if02-event-kbd"
).strip()

# Map keycodes to actual numbers
KEY_MAP = {
    evdev.ecodes.KEY_0: '0',
    evdev.ecodes.KEY_1: '1',
    evdev.ecodes.KEY_2: '2',
    evdev.ecodes.KEY_3: '3',
    evdev.ecodes.KEY_4: '4',
    evdev.ecodes.KEY_5: '5',
    evdev.ecodes.KEY_6: '6',
    evdev.ecodes.KEY_7: '7',
    evdev.ecodes.KEY_8: '8',
    evdev.ecodes.KEY_9: '9',
    evdev.ecodes.KEY_BACKSPACE: 'BACKSPACE',
    evdev.ecodes.KEY_KP0: '0',
    evdev.ecodes.KEY_KP1: '1',
    evdev.ecodes.KEY_KP2: '2',
    evdev.ecodes.KEY_KP3: '3',
    evdev.ecodes.KEY_KP4: '4',
    evdev.ecodes.KEY_KP5: '5',
    evdev.ecodes.KEY_KP6: '6',
    evdev.ecodes.KEY_KP7: '7',
    evdev.ecodes.KEY_KP8: '8',
    evdev.ecodes.KEY_KP9: '9',
    evdev.ecodes.KEY_ENTER: 'ENTER',
    evdev.ecodes.KEY_KPENTER: 'ENTER',
}

async def read_keypad(device_path, station_name):
    while True:
        device = None
        current_input = ""

        try:
            device = evdev.InputDevice(device_path)
            print(f"Reading {station_name} keypad from {device_path}", flush=True)

            # Grab the device so the inputs do not leak into the terminal or GUI.
            device.grab()

            async for event in device.async_read_loop():
                if event.type != evdev.ecodes.EV_KEY or event.value != 1:
                    continue

                key = KEY_MAP.get(event.code)
                if key == 'ENTER':
                    if current_input:
                        requests.post(API_URL, json={
                            "station": station_name,
                            "number": current_input
                        }, timeout=2)
                        current_input = ""
                elif key == 'BACKSPACE':
                    current_input = current_input[:-1]
                elif key:
                    if len(current_input) < MAX_DIGITS:
                        current_input += key
        except Exception as e:
            print(f"Error reading {station_name} keypad at {device_path}: {e}", flush=True)
        finally:
            if device is not None:
                try:
                    device.ungrab()
                except OSError:
                    pass
                device.close()

        await asyncio.sleep(RETRY_SECONDS)

async def main():
    keypads = []

    if DRINKS_DEVICE_PATH:
        keypads.append(read_keypad(DRINKS_DEVICE_PATH, "drinks"))
    if FOOD_DEVICE_PATH:
        keypads.append(read_keypad(FOOD_DEVICE_PATH, "food"))

    if not keypads:
        raise RuntimeError("Set FOOD_DEVICE_PATH and/or DRINKS_DEVICE_PATH")

    await asyncio.gather(*keypads)

if __name__ == "__main__":
    asyncio.run(main())
