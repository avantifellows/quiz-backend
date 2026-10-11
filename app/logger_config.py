import logging
import os
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_LOG_LEVEL = "INFO"


class ISTFormatter(logging.Formatter):
    @staticmethod
    def _converter(*args):
        return datetime.now(tz=IST).timetuple()

    converter = _converter

    def format(self, record):
        # Keep every record on one physical line: request values interpolated into
        # messages (paths, query params) could otherwise forge extra log records.
        return super().format(record).replace("\r", "\\r").replace("\n", "\\n")


def _log_level():
    """LOG_LEVEL env var (e.g. DEBUG, INFO, WARNING); falls back to INFO."""
    name = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper()
    return logging.getLevelNamesMapping().get(name, logging.INFO)


def setup_logger():
    logger = logging.getLogger("quizenginelogger")

    if logger.handlers:
        return logger

    logger.propagate = False

    logger_format = "%(asctime)s IST loglevel=%(levelname)-6s filename=%(filename)s funcName=%(funcName)s() L%(lineno)-4d %(message)s"

    formatter = ISTFormatter(fmt=logger_format, datefmt="%Y-%m-%d %H:%M:%S")

    level = _log_level()
    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(level)
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)
    logger.setLevel(level)

    return logger


def get_logger():
    return logging.getLogger("quizenginelogger")
