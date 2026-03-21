import sys
from pathlib import Path
from loguru import logger


def setup_logger(level: str = "DEBUG", rotation: str = "10 MB", retention: str = "7 days"):
    """Configure loguru logger with file and console output."""
    log_dir = Path(__file__).parent.parent / "log"
    log_dir.mkdir(exist_ok=True)

    logger.remove()

    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    logger.add(
        log_dir / "bot_{time:YYYY-MM-DD}.log",
        level=level,
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    return logger
