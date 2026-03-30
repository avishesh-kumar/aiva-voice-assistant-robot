import logging
from pathlib import Path

LOG_DIR = Path(__file__).parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

def get_logger(name: str, filename: str):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(LOG_DIR / filename)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False
    return logger

