import logging
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(domain):
    Log_Format = "%(levelname)s %(asctime)s - %(message)s"

    logging.basicConfig(filename = f"stemwizard_{domain}.log",
                        # filemode = "w",
                        format = Log_Format,
                        level = logging.DEBUG)

    logger = logging.getLogger()
    return logger
