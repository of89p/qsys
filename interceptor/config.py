from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_URL = "http://127.0.0.1:8080/api/v1/queue"
DEFAULT_LOG_LEVEL = "WARNING"
DEFAULT_RETRY_SECONDS = 5

STATION_DEVICE_ENV = (
    ("drinks", "DRINKS_DEVICE_PATH"),
    ("chicken", "CHICKEN_DEVICE_PATH"),
    ("food", "FOOD_DEVICE_PATH"),
)


@dataclass(frozen=True)
class ConfiguredKeypad:
    station: str
    device_path: str


@dataclass(frozen=True)
class InterceptorConfig:
    queue_url: str
    log_level: str
    accept_row_digits: bool
    retry_seconds: int
    keypads: tuple[ConfiguredKeypad, ...]


def env_truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes", "on"}


def load_config() -> InterceptorConfig:
    load_dotenv(ROOT_DIR / ".env")

    keypads = tuple(
        ConfiguredKeypad(station=station, device_path=device_path)
        for station, env_key in STATION_DEVICE_ENV
        if (device_path := os.getenv(env_key, "").strip())
    )

    return InterceptorConfig(
        queue_url=os.getenv("QSYS_QUEUE_URL", DEFAULT_QUEUE_URL),
        log_level=os.getenv("QSYS_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        accept_row_digits=env_truthy(os.getenv("QSYS_ACCEPT_ROW_DIGITS")),
        retry_seconds=DEFAULT_RETRY_SECONDS,
        keypads=keypads,
    )
