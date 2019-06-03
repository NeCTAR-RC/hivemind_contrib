import logging

logging_level = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARN,
    'ERROR': logging.ERROR,
    }


def logger(logfile, loglevel='INFO'):
    loglevel = logging_level.get(loglevel, logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # for console handler
    handler = logging.StreamHandler()
    handler.setLevel(loglevel)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # for file handler, always set its level to DEBUG
    handler = logging.FileHandler(logfile, "w")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
