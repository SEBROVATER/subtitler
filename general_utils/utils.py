import os
import signal
from functools import cache
from pathlib import Path


@cache
def get_base_dir():
    base_dir = Path(__file__).parent
    while "general_utils" not in (p.name for p in base_dir.iterdir()):
        base_dir = base_dir.parent

    return base_dir


@cache
def is_in_debug():
    """Returns True if there is a DEBUG environment variable with
    value 'True' or 'true', in any other cases returns False"""

    return os.environ.get("DEBUG", "False").lower() == "true"


def load_envs(name: str):
    from dotenv import load_dotenv

    assert name.endswith(".env"), ".env file must end with '.env'"
    load_dotenv(get_base_dir() / name, override=True)


class GracefulKiller:
    is_running = True

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    @staticmethod
    def exit_gracefully(*args):
        GracefulKiller.is_running = False
        print("Exiting...")
