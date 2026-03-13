from __future__ import annotations

import logging
import time
from typing import Callable, Protocol

from .config import load_config
from .service_runner import ServiceRunner


class _Runner(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


def main(*, runner_factory: Callable[[], _Runner] | None = None, sleep_fn: Callable[[float], None] = time.sleep) -> int:
    config = load_config()
    log_level_name = str(config.get("log_level") or "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    factory = runner_factory or (lambda: ServiceRunner(config=config))
    runner = factory()
    runner.start()
    try:
        while True:
            sleep_fn(1.0)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Received keyboard interrupt, stopping service runner.")
    finally:
        runner.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())