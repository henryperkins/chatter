import logging
from logging.config import dictConfig
import os

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

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
            'formatter': 'json' if os.getenv('FLASK_ENV') == 'production' else 'standard',
            'level': log_level,
        },
    },
    'root': {
        'level': log_level,
        'handlers': ['console'],
    },
}

dictConfig(logconfig_dict)
