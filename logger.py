import asyncio
import json
import logging
import logging.config
import time
import uuid
import os

from datetime import datetime

import sanic


class NoHealthzFilter:
    @staticmethod
    def filter(record):
        return '/healthz' not in getattr(record.request, 'path', record.msg)

class KeepAliveTimeoutFilter:
    @staticmethod
    def filter(record):
        return 'KeepAlive Timeout' not in record.msg


class JSONFormatter(logging.Formatter):
    LogRecordFields = None

    def format(self, record):
        record.message = record.getMessage()
        msg = self.formatMessage(record)
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if msg[-1:] != '\n':
                msg += '\n'
            msg += record.exc_text
        if record.stack_info:
            if msg[-1:] != '\n':
                msg += '\n'
            msg += self.formatStack(record.stack_info)

        message = {
            '@timestamp': datetime.fromtimestamp(record.created).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            'level': record.levelname,
            'module': record.module,
            'message': msg,
            'type': getattr(record, 'type', 'log'),
            'logger': record.name
        }
        if self.LogRecordFields is None:
            self.LogRecordFields = {f for f in dir(record) if not f.startswith('__')}
        for key, value in record.__dict__.items():
            if key not in self.LogRecordFields:
                message[key] = value
        add_msg_type_properties(message, record)
        add_task_properties(message)
        return json_string(message)


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

        add_task_properties(message)
        return json_string(message)


def add_msg_type_properties(message: dict, record: logging.LogRecord):
    if message['type'] == 'log':
        if record.funcName is not None:
            message['function'] = record.funcName
        if record.filename is not None:
            message['file'] = record.filename + ':' + str(record.lineno) if record.lineno else record.filename
    elif message['type'] == 'event':
        message['event_type'] = record.event_type


def add_task_properties(message: dict):
    try:
        current_task = asyncio.Task.current_task()
        # TODO make 'context' configurable by __init__(arg) from logging config
        if current_task and hasattr(current_task, 'context'):
            message['request_id'] = current_task.context.get('req_id', '')
            message['session_id'] = current_task.context.get('session_id', '')
    except:  # pylint: disable=bare-except
        pass


def json_string(message: dict):
    try:
        s = json.dumps(message, ensure_ascii=False, separators=(',', ':'))
    except:  # pylint: disable=bare-except
        s = json.dumps({'error': f'Log message not serializabe to json: {message}'})
    return s.replace('\\"', '')


STRING_FORMATTERS = {
    'standard': {
        'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    },
    'request': {
        'format': '%(asctime)s [%(levelname)s] %(name)s: %(request)s'
    }
}


JSON_FORMATTERS = {
    'standard': {
        '()': JSONFormatter
    },
    'request': {
        '()': JSONReqFormatter
    }
}


DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
    },
    'handlers': {
        'default': {
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'filters': ['keepalive_timeout']
        },
        'request': {
            'level': 'INFO',
            'formatter': 'request',
            'class': 'logging.StreamHandler',
            'filters': ['nohealthz']
        },
    },
    'loggers': {
        '': {
            'handlers': ['default'],
            'level': 'DEBUG',
            'propagate': True
        },
        'sanic.root': {
            'handlers': ['default'],
            'level': 'DEBUG',
            'propagate': False
        },
        'sanic.access': {
            'handlers': ['request'],
            'level': 'DEBUG',
            'propagate': False
        },
        'sanic.error': {
            'handlers': ['default'],
            'level': 'DEBUG',
            'propagate': False
        },
    },
    'filters': {
        'nohealthz': {
            '()': NoHealthzFilter
        },
        'keepalive_timeout': {
            '()': KeepAliveTimeoutFilter
        }
    }
}

def get_log(name='root'):
    return logging.getLogger(name)


def setup_logging(app: sanic.Sanic):
    app.config.LOGO = f'Sanic v.{sanic.__version__}'
    app.config.ACCESS_LOG = False
    log_config = DEFAULT_LOGGING.copy()
    log_config['formatters'] = STRING_FORMATTERS
    if os.environ.get('KUBERNETES_PORT'):
        # running inside kubernetes, setup json logging
        log_config['formatters'] = JSON_FORMATTERS

    logging.config.dictConfig(log_config)
    asyncio.get_event_loop().set_task_factory(_task_factory)
    req_logger = logging.getLogger('sanic.access')

    # Middleware to start a timer to gather request length.
    # Also generate a request ID, should really make request ID configurable
    @app.middleware('request')
    async def log_json_pre(request):
        """
        Setup unique request ID and start time
        :param request: Web request
        """
        current_task = asyncio.current_task()
        if current_task:
            if hasattr(current_task, 'context'):
                current_task.context['req_id'] = str(uuid.uuid4())
                current_task.context['req_start'] = time.perf_counter()
            else:
                current_task.context = {
                    'req_id': str(uuid.uuid4()),
                    'req_start': time.perf_counter()
                }

    # This performs the role of access logs
    @app.middleware('response')
    async def log_json_post(request, response):
        """
        Calculate response time, then log access json
        :param request: Web request
        :param response: HTTP Response
        :return:
        """
        req_id = 'unknown'
        time_taken = -1

        current_task = asyncio.current_task()
        if hasattr(current_task, 'context'):
            req_id = current_task.context['req_id']
            time_taken = time.perf_counter() - current_task.context['req_start']

        status_code = response.status
        level = logging.INFO if 0 < status_code < 400 else logging.WARNING
        req_logger.log(level, None, extra={'request': request, 'response': response, 'time': time_taken, 'req_id': req_id})


def _task_factory(loop: asyncio.AbstractEventLoop, coro: asyncio.coroutine) -> asyncio.Task:
    """
    see task_factory implementation in CPython at
    https://github.com/python/cpython/blob/master/Lib/asyncio/base_events.py#L407
    """
    task = asyncio.Task(coro, loop=loop)
    if task._source_traceback:  # pylint: disable=protected-access
        del task._source_traceback[-1]  # pylint: disable=protected-access,unsupported-delete-operation

    # Share context with new task if possible
    current_task = asyncio.current_task(loop=loop)
    if hasattr(current_task, 'context'):
        setattr(task, 'context', current_task.context)

    return task
