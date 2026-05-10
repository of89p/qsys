import evdev
import asyncio
import logging
import os
import requests

API_URL = os.getenv("QSYS_QUEUE_URL", "http://127.0.0.1:8080/api/queue")
LOG_LEVEL = os.getenv("QSYS_LOG_LEVEL", "INFO").upper()
ACCEPT_ROW_DIGITS = os.getenv("QSYS_ACCEPT_ROW_DIGITS", "").lower() in {
    "1", "true", "yes", "on"
}
RETRY_SECONDS = 5
MAX_DIGITS = 3

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("qsys.interceptor")

# Set these from the systemd service. For now, ls-logs.txt shows one attached
# keyboard receiver, so the default assigns it to the food station.
DRINKS_DEVICE_PATH = os.getenv("DRINKS_DEVICE_PATH", "").strip()
FOOD_DEVICE_PATH = os.getenv(
    "FOOD_DEVICE_PATH",
    "/dev/input/by-id/usb-Logitech_USB_Receiver-if02-event-kbd"
).strip()

# Keypad digit keycodes. Normal row digits are ignored by default so a regular
# keyboard can keep working while this process observes the input device.
KEYPAD_KEY_MAP = {
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
    evdev.ecodes.KEY_KPENTER: 'ENTER',
}

ROW_DIGIT_KEY_MAP = {
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
}

BUFFER_CONTROL_KEY_MAP = {
    evdev.ecodes.KEY_ENTER: 'ENTER',
    evdev.ecodes.KEY_BACKSPACE: 'BACKSPACE',
}

def key_name(event_code):
    name = evdev.ecodes.KEY.get(event_code, str(event_code))
    if isinstance(name, (list, tuple)):
        return "/".join(name)
    return name

def mapped_key_for_event(event_code, current_input):
    key = KEYPAD_KEY_MAP.get(event_code)
    if key is not None:
        return key

    if ACCEPT_ROW_DIGITS:
        key = ROW_DIGIT_KEY_MAP.get(event_code)
        if key is not None:
            return key

    if current_input:
        return BUFFER_CONTROL_KEY_MAP.get(event_code)

    return None

def submit_number(station_name, number):
    try:
        response = requests.post(API_URL, json={
            "station": station_name,
            "number": number,
        }, timeout=2)
    except requests.RequestException as exc:
        logger.error(
            "%s keypad could not submit number=%s to %s: %s. "
            "Start the server in another terminal with: .venv/bin/python server.py",
            station_name,
            number,
            API_URL,
            exc,
        )
        return False

    if not response.ok:
        logger.error(
            "%s keypad submit rejected number=%s status_code=%s response=%s",
            station_name,
            number,
            response.status_code,
            response.text[:200],
        )
        return False

    logger.info(
        "%s keypad submitted number=%s status_code=%s",
        station_name,
        number,
        response.status_code,
    )
    return True

async def read_keypad(device_path, station_name):
    while True:
        device = None
        current_input = ""

        try:
            device = evdev.InputDevice(device_path)
            logger.info(
                "Reading %s keypad from %s without exclusive grab; non-keypad "
                "input will pass through to the OS",
                station_name,
                device_path,
            )

            async for event in device.async_read_loop():
                if event.type != evdev.ecodes.EV_KEY or event.value != 1:
                    continue

                event_name = key_name(event.code)
                key = mapped_key_for_event(event.code, current_input)
                if key is None:
                    logger.debug(
                        "%s keypad ignored non-keypad key code=%s name=%s",
                        station_name,
                        event.code,
                        event_name,
                    )
                    continue

                logger.info(
                    "%s keypad intercepted key=%s code=%s name=%s buffer=%s",
                    station_name,
                    key,
                    event.code,
                    event_name,
                    current_input or "-",
                )

                if key == 'ENTER':
                    if current_input:
                        if submit_number(station_name, current_input):
                            current_input = ""
                        else:
                            logger.info(
                                "%s keypad buffer retained=%s",
                                station_name,
                                current_input,
                            )
                    else:
                        logger.info("%s keypad ignored ENTER with empty buffer", station_name)
                elif key == 'BACKSPACE':
                    current_input = current_input[:-1]
                    logger.info("%s keypad buffer=%s", station_name, current_input or "-")
                elif key:
                    if len(current_input) < MAX_DIGITS:
                        current_input += key
                        logger.info("%s keypad buffer=%s", station_name, current_input)
                    else:
                        logger.info(
                            "%s keypad ignored digit=%s because buffer is full (%s)",
                            station_name,
                            key,
                            current_input,
                        )
        except PermissionError:
            logger.error(
                "Permission denied reading %s keypad at %s. For a manual test, run "
                "the interceptor with sudo or add this user to the input group.",
                station_name,
                device_path,
            )
        except Exception:
            logger.exception("Error reading %s keypad at %s", station_name, device_path)
        finally:
            if device is not None:
                device.close()

        await asyncio.sleep(RETRY_SECONDS)

async def main():
    keypads = []
    logger.info("Queue endpoint is %s", API_URL)

    if DRINKS_DEVICE_PATH:
        keypads.append(read_keypad(DRINKS_DEVICE_PATH, "drinks"))
    if FOOD_DEVICE_PATH:
        keypads.append(read_keypad(FOOD_DEVICE_PATH, "food"))

    if not keypads:
        raise RuntimeError("Set FOOD_DEVICE_PATH and/or DRINKS_DEVICE_PATH")

    await asyncio.gather(*keypads)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interceptor stopped")
