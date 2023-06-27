import logging
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


class ISTFormatter(logging.Formatter):
    @staticmethod
    def _converter(*args):
        return datetime.now(tz=IST).timetuple()

    converter = _converter


def setup_logger():
    logger = logging.getLogger("quizenginelogger")

    # https://stackoverflow.com/questions/50909824/getting-logs-twice-in-aws-lambda-function
    logger.propagate = False

    logger_format = "%(asctime)s IST loglevel=%(levelname)-6s filename=%(filename)s funcName=%(funcName)s() L%(lineno)-4d %(message)s call_trace=%(pathname)s L%(lineno)-4d"

    formatter = ISTFormatter(fmt=logger_format, datefmt="%Y-%m-%d %H:%M:%S")

    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logging.DEBUG)
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)
    logger.setLevel(logging.DEBUG)

    return logger


def get_logger():
    return logging.getLogger("quizenginelogger")
