from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import requests

logger = logging.getLogger("qsys.interceptor.queue_client")


@dataclass(frozen=True)
class QueueSubmission:
    station: str
    number: str


class QueueClient:
    def __init__(self, api_url: str, timeout_seconds: int = 2) -> None:
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds

    def submit(self, submission: QueueSubmission) -> bool:
        try:
            response = requests.post(
                self.api_url,
                json=asdict(submission),
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            logger.error(
                "%s keypad could not submit number=%s to %s: %s",
                submission.station,
                submission.number,
                self.api_url,
                exc,
            )
            return False

        if not response.ok:
            logger.error(
                "%s keypad submit rejected number=%s status_code=%s response=%s",
                submission.station,
                submission.number,
                response.status_code,
                response.text[:200],
            )
            return False

        logger.info(
            "%s keypad submitted number=%s status_code=%s",
            submission.station,
            submission.number,
            response.status_code,
        )
        return True
