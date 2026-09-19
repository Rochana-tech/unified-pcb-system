import logging
import sys

from layers.layer1.config import config


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-22s | %(message)s", "%H:%M:%S"
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    return logger
