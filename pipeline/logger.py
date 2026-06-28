"""
logger.py
Shared logging configuration. Every pipeline script calls get_logger(__name__)
to get a consistently configured logger that writes to both console and file.
"""
import logging
from pipeline.config import LOG_LEVEL, LOG_FILE, resolve_path


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        # Already configured (e.g. re-imported) -- don't add duplicate handlers.
        return logger

    logger.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_path = resolve_path(LOG_FILE)
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
