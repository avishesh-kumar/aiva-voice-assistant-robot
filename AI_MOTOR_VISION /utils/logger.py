import logging
from pathlib import Path


def setup_logger(
    name: str,
    log_file: str = "system.log",
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Create and return a configured logger.

    - Logs to logs/<log_file>
    - Also logs to console
    - Safe to call multiple times
    """

    # Resolve project root (utils/ -> project root)
    project_root = Path(__file__).parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # File handler
    file_handler = logging.FileHandler(log_dir / log_file)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.propagate = False  # very important

    return logger
