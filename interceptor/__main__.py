from __future__ import annotations

import asyncio
import logging

from interceptor.config import load_config
from interceptor.keypad import Keypad
from interceptor.queue_client import QueueClient


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.WARNING),
        format="%(asctime)s %(levelname)s %(message)s",
    )


async def main() -> None:
    config = load_config()
    configure_logging(config.log_level)
    logger = logging.getLogger("qsys.interceptor")
    logger.info("Queue endpoint is %s", config.queue_url)

    if not config.keypads:
        raise RuntimeError(
            "Set at least one of FOOD_DEVICE_PATH, DRINKS_DEVICE_PATH, "
            "or CHICKEN_DEVICE_PATH"
        )

    queue_client = QueueClient(config.queue_url)
    await asyncio.gather(
        *[
            Keypad(
                device_path=keypad.device_path,
                station=keypad.station,
                queue_client=queue_client,
                accept_row_digits=config.accept_row_digits,
                retry_seconds=config.retry_seconds,
            ).run()
            for keypad in config.keypads
        ]
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger("qsys.interceptor").info("Interceptor stopped")
