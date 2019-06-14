import asyncio
import logging
import time
import uuid

from datetime import datetime

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


class JSONReqFormatter(logging.Formatter):
    def format(self, record):
        host = record.request.host
        if record.request.headers:
            host = record.request.headers.get('X-Forwarded-For', host)
        millis = round(record.time, 2)
        status = getattr(record.response, 'status', '')
        msg = f'{record.request.method} {record.request.path} {status}'
        message = {
            '@timestamp': datetime.fromtimestamp(record.created).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            'level': record.levelname,
            'message': msg,
            'type': 'access',
            'method': record.request.method,
            'path': record.request.path,
            'remote': f'{record.request.ip}:{record.request.port}',
            'host': host,
            'request_ms': millis,
            'user_agent': record.request.headers.get('user-agent'),
            'logger': record.name
        }

        if record.response is not None:  # not Websocket
            message['status_code'] = status
            if hasattr(record.response, 'body'):
                message['length'] = len(record.response.body)
            else:
                message['length'] = -1
        else:
            message['type'] = 'ws_access'

        logger.add_task_properties(message)
        return logger.json_string(message)


def setup_sanic_logging(app: sanic.Sanic):
    config = logger.configuration()
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
            '()': JSONReqFormatter
        }

    logger.setup_logging(config=config)

    app.config.LOGO = f'Sanic v.{sanic.__version__}'
    app.config.ACCESS_LOG = False

    req_logger = logging.getLogger('sanic.access')

    # Middleware to start a timer to gather request length.
    # Also generate a request ID, should really make request ID configurable
    @app.middleware('request')
    async def log_json_pre(request):
        """
        Setup unique request ID and start time
        :param request: Web request
        """
        set_context_property('req_id', str(uuid.uuid4()))
        set_context_property('req_start', time.perf_counter())

    # This performs the role of access logs
    @app.middleware('response')
    async def log_json_post(request, response):
        """
        Calculate response time, then log access json
        :param request: Web request
        :param response: HTTP Response
        :return:
        """
        req_id = get_context_property('req_id') or 'unknown'
        time_taken = time.perf_counter() - (get_context_property('req_start') or -1)
        status_code = response.status
        level = logging.INFO if 0 < status_code < 400 else logging.WARNING
        req_logger.log(level, None, extra={
            'request': request,
            'response': response,
            'time': time_taken,
            'req_id': req_id
        })


def set_context_property(name, value):
    current_task = asyncio.current_task()
    if current_task:
        if hasattr(current_task, 'context'):
            current_task.context[name] = value
        else:
            current_task.context = dict([(name, value)])
    else:
        logging.error('No current_task available from asyncio, is logging set up?')


def get_context_property(name):
    current_task = asyncio.current_task()
    if current_task:
        if hasattr(current_task, 'context'):
            return current_task.context.get(name)
    return None
