from .logger import setup_logging, get_log
from .sanic_logger import setup_sanic_logging

__all__ = (setup_logging, setup_sanic_logging, get_log)
