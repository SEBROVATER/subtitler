import logging.config
from pathlib import Path

from general_utils.utils import get_base_dir, is_in_debug


def get_logger(name: str, with_file: bool = True):
    debug = is_in_debug()
    if debug:
        name = f"dev.{name}"

    base_dir = get_base_dir()
    log_path = Path(f"{base_dir}/logs/{name}.log")
    log_path.parent.mkdir(exist_ok=True)

    level = "DEBUG" if debug else "INFO"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "[{asctime}] {levelname:^7} | def {funcName}() | {message}",
                "style": "{",
            },
        },
        "handlers": {
            "file": {
                "level": "DEBUG",
                "class": "logging.FileHandler",
                "filename": log_path.as_posix(),
                "encoding": "utf-8",
                "formatter": "verbose",
            },
            "console": {
                "level": level,
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
        },
        "root": {
            "level": "DEBUG",
        },
        "loggers": {
            name: {
                "handlers": ["file", "console"] if with_file else ["console"],
                "level": "DEBUG",
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(config)

    return logging.getLogger(name)
