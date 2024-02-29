import logging
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler
import os
import random

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

    # Define the logs folder and log filename
    pid = os.getpid()
    machine_ip = os.getenv("HOST_IP", "localhost")
    logs_folder = "../logs"
    log_filename = f"app_{machine_ip}_{pid}.log"

    # Create the logs folder if it doesn't exist
    if not os.path.exists(logs_folder):
        os.makedirs(logs_folder)

    log_filepath = os.path.join(logs_folder, log_filename)

    # Custom namer function to add timestamp to rotated log files
    def log_namer(name):
        name_parts = name.split("_")
        app = name_parts[0]
        machine_ip = name_parts[1]
        pid = name_parts[2].split(".")[0]
        # app, machine_ip, pid
        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        return f"{app}_{machine_ip}_{pid}_{timestamp}.log"

    # Create the TimedRotatingFileHandler with the custom filename
    random_interval = random.randint(5, 8)
    
    fileHandler = TimedRotatingFileHandler(
        log_filepath, when="M", interval=random_interval, backupCount=100
    )
    fileHandler.setFormatter(formatter)
    fileHandler.setLevel(logging.INFO)
    fileHandler.namer = log_namer
    logger.addHandler(fileHandler)

    # Set the logger level
    logger.setLevel(logging.INFO)

    return logger


def get_logger():
    return logging.getLogger("QuizBackend")
