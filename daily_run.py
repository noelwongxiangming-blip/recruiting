"""Scheduled entry point — wraps main.run() with file logging and timeout.

Writes one log file per day to logs/YYYY-MM-DD.log so you can see exactly
what happened on any given run: which sources fired, how many candidates
each source returned, what the filters rejected, what got written, and
any errors with full tracebacks.

Also echoes to stdout so console schedulers still see output.

Used by scheduling/ templates (cron, Task Scheduler, launchd, GitHub Actions).
"""

import io
import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

MAX_RUNTIME_SECONDS = 15 * 60
LOG_DIR = Path(__file__).parent / "logs"


def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    logger = logging.getLogger("startup_radar")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


class _LogStream(io.TextIOBase):
    """Redirect `print()` output into the logger so main.py's step-by-step
    messages land in logs/YYYY-MM-DD.log alongside the structured entries."""
    encoding = "utf-8"

    def __init__(self, log: logging.Logger):
        self._log = log

    def write(self, msg: str) -> int:
        for line in msg.rstrip().splitlines():
            stripped = line.strip()
            if stripped:
                self._log.info(stripped)
        return len(msg)

    def flush(self) -> None:
        pass


def main() -> int:
    os.chdir(Path(__file__).parent)
    logger = _setup_logging()
    logger.info("Startup Radar daily run starting")

    def _timeout():
        logger.error(f"Run timed out after {MAX_RUNTIME_SECONDS // 60} minutes")
        os._exit(1)

    timer = threading.Timer(MAX_RUNTIME_SECONDS, _timeout)
    timer.daemon = True
    timer.start()

    old_stdout = sys.stdout
    sys.stdout = _LogStream(logger)

    try:
        from main import run
        rc = run()
        sys.stdout = old_stdout
        timer.cancel()
        logger.info("Daily run completed successfully")
        return rc
    except Exception as e:
        sys.stdout = old_stdout
        timer.cancel()
        msg = str(e).lower()
        if "token" in msg or "credentials" in msg or "refresh" in msg:
            logger.error(f"OAuth token expired or invalid: {e}")
            logger.error("Delete token.json and run `python main.py` manually to re-authenticate.")
        else:
            logger.error(f"Daily run failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
