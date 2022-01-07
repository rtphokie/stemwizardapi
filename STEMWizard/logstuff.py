import logging

Log_Format = "%(levelname)s %(asctime)s - %(message)s"

logging.basicConfig(filename = "stemwizard.log",
                    # filemode = "w",
                    format = Log_Format,
                    level = logging.DEBUG)

logger = logging.getLogger()
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
