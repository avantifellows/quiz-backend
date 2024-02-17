import logging
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler

IST = timezone(timedelta(hours=5, minutes=30))


class ISTFormatter(logging.Formatter):
    @staticmethod
    def _converter(*args):
        return datetime.now(tz=IST).timetuple()

    converter = _converter


def setup_logger():
    logger_name = "QuizBackend"
    logger = logging.getLogger(logger_name)

    # https://stackoverflow.com/questions/50909824/getting-logs-twice-in-aws-lambda-function
    # # Avoid duplicate log entries
    logger.propagate = False

    logger_format = "%(asctime)s IST loglevel=%(levelname)-6s filename=%(filename)s funcName=%(funcName)s() L%(lineno)-4d %(message)s call_trace=%(pathname)s L%(lineno)-4d"

    formatter = ISTFormatter(fmt=logger_format, datefmt="%Y-%m-%d %H:%M:%S")

    # for debugging
    # consoleHandler = logging.StreamHandler()
    # consoleHandler.setLevel(logging.DEBUG)
    # consoleHandler.setFormatter(formatter)
    # logger.addHandler(consoleHandler)

    # File handler with log rotation
    fileHandler = TimedRotatingFileHandler(
        "../app.log", when="midnight", interval=1, backupCount=30
    )
    fileHandler.setFormatter(formatter)
    fileHandler.setLevel(logging.DEBUG)
    logger.addHandler(fileHandler)

    # Set the logger level
    logger.setLevel(logging.DEBUG)

    return logger


def get_logger():
    return logging.getLogger("quizenginelogger")
