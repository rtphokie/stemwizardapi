import logging
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
from logging.handlers import TimedRotatingFileHandler


def get_logger(domain, level=logging.DEBUG):
    path=f"logs/stemwizard_{domain}.log"
    if '.log' not in path:
        path += '.log'
    logger = logging.getLogger(path)
    logger.setLevel(level)
    formatter = logging.Formatter("%(asctime)s [%(filename)15s:%(lineno)3s - %(funcName)15s] %(levelname)-8s %(message)s")
    logHandler = TimedRotatingFileHandler(path, when='D', interval=1, backupCount=7)
    logHandler.setLevel(level)
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    return logger
