from .logger import setup_logging, get_log, getLogger
exports = [setup_logging, get_log, getLogger]
try:
    from .sanic_logger import setup_sanic_logging
    exports += setup_sanic_logging
except:
    # no sanic available
    pass

__all__ = tuple(exports)
