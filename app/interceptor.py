import asyncio
import logging
import os
from pathlib import Path

import evdev
import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

API_URL = os.getenv("QSYS_QUEUE_URL", "http://127.0.0.1:8080/api/queue")
LOG_LEVEL = os.getenv("QSYS_LOG_LEVEL", "INFO").upper()
ACCEPT_ROW_DIGITS = os.getenv("QSYS_ACCEPT_ROW_DIGITS", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RETRY_SECONDS = 5
MAX_DIGITS = 3

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("qsys.interceptor")

# Set these from .env. Generate that file with scripts/update_env_from_ls.py.
DRINKS_DEVICE_PATH = os.getenv("DRINKS_DEVICE_PATH", "").strip()
CHICKEN_DEVICE_PATH = os.getenv("CHICKEN_DEVICE_PATH", "").strip()
FOOD_DEVICE_PATH = os.getenv("FOOD_DEVICE_PATH", "").strip()

# Keypad digit keycodes. Normal row digits are ignored by default so a regular
# keyboard can keep working while this process observes the input device.
KEYPAD_KEY_MAP = {
    evdev.ecodes.KEY_KP0: "0",
    evdev.ecodes.KEY_KP1: "1",
    evdev.ecodes.KEY_KP2: "2",
    evdev.ecodes.KEY_KP3: "3",
    evdev.ecodes.KEY_KP4: "4",
    evdev.ecodes.KEY_KP5: "5",
    evdev.ecodes.KEY_KP6: "6",
    evdev.ecodes.KEY_KP7: "7",
    evdev.ecodes.KEY_KP8: "8",
    evdev.ecodes.KEY_KP9: "9",
    evdev.ecodes.KEY_KPENTER: "ENTER",
}

ROW_DIGIT_KEY_MAP = {
    evdev.ecodes.KEY_0: "0",
    evdev.ecodes.KEY_1: "1",
    evdev.ecodes.KEY_2: "2",
    evdev.ecodes.KEY_3: "3",
    evdev.ecodes.KEY_4: "4",
    evdev.ecodes.KEY_5: "5",
    evdev.ecodes.KEY_6: "6",
    evdev.ecodes.KEY_7: "7",
    evdev.ecodes.KEY_8: "8",
    evdev.ecodes.KEY_9: "9",
}

BUFFER_CONTROL_KEY_MAP = {
    evdev.ecodes.KEY_ENTER: "ENTER",
    evdev.ecodes.KEY_BACKSPACE: "BACKSPACE",
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
        response = requests.post(
            API_URL,
            json={
                "station": station_name,
                "number": number,
            },
            timeout=2,
        )
    except requests.RequestException as exc:
        logger.error(
            "%s keypad could not submit number=%s to %s: %s. "
            "Start the server in another terminal with: .venv/bin/python app/server.py",
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
        invalid_input = False

        try:
            device = evdev.InputDevice(device_path)
            logger.debug(
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

                logger.debug(
                    "%s keypad intercepted key=%s code=%s name=%s buffer=%s",
                    station_name,
                    key,
                    event.code,
                    event_name,
                    current_input or "-",
                )

                if key == "ENTER":
                    if invalid_input:
                        logger.debug(
                            "%s keypad discarded invalid input=%s; ready for a new entry",
                            station_name,
                            current_input,
                        )
                        current_input = ""
                        invalid_input = False
                    elif current_input:
                        if submit_number(station_name, current_input):
                            current_input = ""
                        else:
                            logger.debug(
                                "%s keypad buffer retained=%s",
                                station_name,
                                current_input,
                            )
                    else:
                        logger.debug(
                            "%s keypad ignored ENTER with empty buffer", station_name
                        )
                elif key == "BACKSPACE":
                    if invalid_input:
                        logger.debug(
                            "%s keypad ignored BACKSPACE because input is invalid "
                            "until ENTER is pressed",
                            station_name,
                        )
                    else:
                        current_input = current_input[:-1]
                        logger.debug(
                            "%s keypad buffer=%s", station_name, current_input or "-"
                        )
                elif key:
                    if invalid_input:
                        logger.debug(
                            "%s keypad ignored digit=%s because input is invalid "
                            "until ENTER is pressed",
                            station_name,
                            key,
                        )
                    elif len(current_input) < MAX_DIGITS:
                        current_input += key
                        logger.debug("%s keypad buffer=%s", station_name, current_input)
                    else:
                        invalid_input = True
                        logger.debug(
                            "%s keypad marked input invalid after digit=%s exceeded "
                            "%s digits; press ENTER to reset",
                            station_name,
                            key,
                            MAX_DIGITS,
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
    if CHICKEN_DEVICE_PATH:
        keypads.append(read_keypad(CHICKEN_DEVICE_PATH, "chicken"))
    if FOOD_DEVICE_PATH:
        keypads.append(read_keypad(FOOD_DEVICE_PATH, "food"))

    if not keypads:
        raise RuntimeError(
            "Set at least one of FOOD_DEVICE_PATH, DRINKS_DEVICE_PATH, "
            "or CHICKEN_DEVICE_PATH"
        )

    await asyncio.gather(*keypads)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interceptor stopped")
