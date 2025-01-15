import logging  # noqa: F401
from logging.config import dictConfig
import os
from logging.handlers import RotatingFileHandler  # noqa: F401

# Create logs directory if it doesn't exist
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logconfig_dict = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        },
        'json': {
            '()': 'logging_config.JsonFormatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'level': 'DEBUG',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'standard',
            'filename': os.path.join(LOG_DIR, 'gunicorn.log'),
            'maxBytes': 20 * 1024 * 1024,  # 20 MB
            'backupCount': 5,
            'level': 'DEBUG',
        },
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['console', 'file'],
    },
    'loggers': {
        'gunicorn.error': {
            'level': 'DEBUG',
            'handlers': ['file'],
            'propagate': False,
        },
        'gunicorn.access': {
            'level': 'DEBUG',
            'handlers': ['file'],
            'propagate': False,
        },
        'chat_api': {
            'level': 'DEBUG',
            'handlers': ['file'],
            'propagate': False,
        },
        'user_actions': {
            'level': 'DEBUG',
            'handlers': ['file'],
            'propagate': False,
        },
        'app': {
            'level': 'DEBUG',
            'handlers': ['file'],
            'propagate': False,
        },
        'models': {
            'level': 'DEBUG',
            'handlers': ['file'],
            'propagate': False,
        },
        'database': {
            'level': 'DEBUG',
            'handlers': ['file'],
            'propagate': False,
        },
    },
}

dictConfig(logconfig_dict)
