import logging
import time
import uuid

import sanic

from . import logger


class NoHealthzFilter:
    @staticmethod
    def filter(record):
        return '/healthz' not in getattr(record.request, 'path', record.msg)


class KeepAliveTimeoutFilter:
    @staticmethod
    def filter(record):
        return 'KeepAlive Timeout' not in record.msg


async def log_json_pre(request):
    """
    Setup unique request ID and start time
    :param request: Web request
    """
    request['request_id'] = str(uuid.uuid4())
    request['request_start'] = time.perf_counter()


async def log_json_post(request, response):
    """
    Calculate response time, then log access json
    :param request: Web request
    :param response: HTTP Response
    :return:
    """
    time_taken = time.perf_counter() - (request['request_start'] or -1)
    level = logging.INFO if 0 < response.status < 400 else logging.WARNING
    msg = f'{request.method} {request.path} {response.status}'
    logging.getLogger('sanic.access').log(level, msg, extra={
        'request': request,
        'response': response,
        'request_time': time_taken,
        'request_id': request['request_id']
    })


def setup_sanic_logging(app: sanic.Sanic, service=None):
    config = logger.configuration(service)
    config['handlers']['default']['filters'] = ['keepalive_timeout']
    config['handlers']['request'] = {
        'level': 'INFO',
        'formatter': 'request',
        'class': 'logging.StreamHandler',
        'filters': ['nohealthz']
    }
    config['filters'] = {
        'nohealthz': {
            '()': NoHealthzFilter
        },
        'keepalive_timeout': {
            '()': KeepAliveTimeoutFilter
        }
    }
    config['loggers']['sanic.root'] = {
        'handlers': ['default'],
        'level': 'DEBUG',
        'propagate': False
    }
    config['loggers']['sanic.access'] = {
        'handlers': ['request'],
        'level': 'DEBUG',
        'propagate': False
    }
    config['loggers']['sanic.error'] = {
        'handlers': ['default'],
        'level': 'DEBUG',
        'propagate': False
    }

    if config['_type'] == 'string':
        config['formatters']['request'] = {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(request)s'
        }
    else:
        config['formatters']['request'] = {
            '()': logger.JSONFormatter,
            'service': service
        }

    logger.setup_logging(config=config)

    app.config.LOGO = f'Sanic v.{sanic.__version__}'
    app.config.ACCESS_LOG = False

    app.register_middleware(log_json_pre, 'request')
    app.register_middleware(log_json_post, 'response')
