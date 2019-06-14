import asyncio
import json
import logging
import logging.config
import os

from datetime import datetime


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


DEFAULT_LOGGING = {
    'version': 1,
    '_type': 'string',
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        }
    },
    'handlers': {
        'default': {
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        '': {
            'handlers': ['default'],
            'level': 'DEBUG',
            'propagate': True
        }
    }
}


def configuration():
    """Get the dict config to override any settings, pass the modified
    dict to setup_logging."""
    config = DEFAULT_LOGGING.copy()
    if os.environ.get('KUBERNETES_PORT'):
        # running inside kubernetes, setup json logging
        config['_type'] = 'json'
        config['formatters'] = {
            'standard': {
                '()': JSONFormatter
            }
        }

    return config


def get_log(name='root'):
    return logging.getLogger(name)


def getLogger(name='root'):
    return logging.getLogger(name)


def setup_logging(config=None):
    asyncio.get_event_loop().set_task_factory(_task_factory)
    if not config:
        config = configuration()
    logging.config.dictConfig(config)


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
