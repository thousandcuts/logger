import json
import logging
import logging.config
import math
import os


class JSONFormatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        self.service = kwargs.pop('service', None) or ''
        self.app_id = kwargs.pop('app_id', None) or ''
        super().__init__(*args, **kwargs)

    def format(self, record):
        subsecond, second = math.modf(record.created)
        msg = {
            'timestamp': {'seconds': int(second), 'nanos': int(subsecond * 1e9)},
            'module': record.module,
            'message': super().format(record),
            'thread': record.thread,
            'logger': record.name,
            'severity': record.levelname,
            'service': self.service or '',
            'app_id': getattr(record, 'app_id', self.app_id),
        }
        if record.funcName is not None:
            msg['function'] = record.funcName
            msg['lineno'] = record.lineno
        if record.filename is not None:
            msg['file'] = f'{record.filename}:{record.lineno}' if record.lineno else record.filename
        if hasattr(record, 'request_id'):
            msg['request_id'] = record.request_id
            msg['request_time'] = record.time_taken
        return json_string(msg)


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


def configuration(service=None) -> dict:
    """Get the dict config to override any settings, pass the modified
    dict to setup_logging."""
    config = DEFAULT_LOGGING.copy()
    if os.environ.get('KUBERNETES_PORT'):
        # running inside kubernetes, setup json logging
        config['_type'] = 'json'
        config['formatters'] = {
            'standard': {
                '()': JSONFormatter,
                'service': service
            }
        }

    return config


def get_log(name='root'):
    return logging.getLogger(name)


def getLogger(name='root'):
    return logging.getLogger(name)


def setup_logging(config=None, service=None):
    if not config:
        config = configuration(service)
    logging.config.dictConfig(config)
