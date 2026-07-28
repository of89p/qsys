from __future__ import annotations

import asyncio
import logging

import evdev

from interceptor.queue_client import QueueClient, QueueSubmission

logger = logging.getLogger("qsys.interceptor.keypad")

MAX_DIGITS = 3

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


def key_name(event_code: int) -> str:
    name = evdev.ecodes.KEY.get(event_code, str(event_code))
    if isinstance(name, (list, tuple)):
        return "/".join(name)
    return str(name)


class Keypad:
    def __init__(
        self,
        device_path: str,
        station: str,
        queue_client: QueueClient,
        accept_row_digits: bool,
        retry_seconds: int,
    ) -> None:
        self.device_path = device_path
        self.station = station
        self.queue_client = queue_client
        self.accept_row_digits = accept_row_digits
        self.retry_seconds = retry_seconds

    def mapped_key_for_event(self, event_code: int, current_input: str) -> str | None:
        key = KEYPAD_KEY_MAP.get(event_code)
        if key is not None:
            return key

        if self.accept_row_digits:
            key = ROW_DIGIT_KEY_MAP.get(event_code)
            if key is not None:
                return key

        if current_input:
            return BUFFER_CONTROL_KEY_MAP.get(event_code)

        return None

    async def run(self) -> None:
        while True:
            device = None
            current_input = ""
            invalid_input = False

            try:
                device = evdev.InputDevice(self.device_path)
                logger.debug(
                    "Reading %s keypad from %s without exclusive grab",
                    self.station,
                    self.device_path,
                )

                async for event in device.async_read_loop():
                    if event.type != evdev.ecodes.EV_KEY or event.value != 1:
                        continue

                    event_name = key_name(event.code)
                    key = self.mapped_key_for_event(event.code, current_input)
                    if key is None:
                        logger.debug(
                            "%s keypad ignored key code=%s name=%s",
                            self.station,
                            event.code,
                            event_name,
                        )
                        continue

                    logger.debug(
                        "%s keypad key=%s code=%s name=%s buffer=%s",
                        self.station,
                        key,
                        event.code,
                        event_name,
                        current_input or "-",
                    )

                    if key == "ENTER":
                        if invalid_input:
                            logger.debug(
                                "%s keypad discarded invalid input=%s",
                                self.station,
                                current_input,
                            )
                            current_input = ""
                            invalid_input = False
                        elif current_input:
                            submission = QueueSubmission(
                                station=self.station,
                                number=current_input,
                            )
                            if self.queue_client.submit(submission):
                                current_input = ""
                            else:
                                logger.debug(
                                    "%s keypad buffer retained=%s",
                                    self.station,
                                    current_input,
                                )
                        else:
                            logger.debug("%s keypad ignored empty ENTER", self.station)
                    elif key == "BACKSPACE":
                        if invalid_input:
                            logger.debug(
                                "%s keypad ignored BACKSPACE for invalid input",
                                self.station,
                            )
                        else:
                            current_input = current_input[:-1]
                            logger.debug(
                                "%s keypad buffer=%s",
                                self.station,
                                current_input or "-",
                            )
                    elif invalid_input:
                        logger.debug(
                            "%s keypad ignored digit=%s while input is invalid",
                            self.station,
                            key,
                        )
                    elif len(current_input) < MAX_DIGITS:
                        current_input += key
                        logger.debug("%s keypad buffer=%s", self.station, current_input)
                    else:
                        invalid_input = True
                        logger.debug(
                            "%s keypad marked input invalid after exceeding %s digits",
                            self.station,
                            MAX_DIGITS,
                        )
            except PermissionError:
                logger.error(
                    "Permission denied reading %s keypad at %s. Add the service "
                    "user to the input group or run the interceptor with sudo.",
                    self.station,
                    self.device_path,
                )
            except Exception:
                logger.exception(
                    "Error reading %s keypad at %s",
                    self.station,
                    self.device_path,
                )
            finally:
                if device is not None:
                    device.close()

            await asyncio.sleep(self.retry_seconds)
