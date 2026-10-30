"""Scheduled-task entry point: `python -m app.sweeps run_once`.

Production runs this daily at 9am as a one-off ECS task using the API image.
"""

import argparse
import logging

from app.db.session import SessionLocal
from app.services.sweeps import run_match_sweep

log = logging.getLogger("app.sweeps")


def run_once() -> None:
    with SessionLocal.begin() as db:
        result = run_match_sweep(db)
    log.info("match sweep: %s", result)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m app.sweeps")
    parser.add_argument("command", choices=["run_once"])
    parser.parse_args()
    run_once()


if __name__ == "__main__":
    main()
