import os
import logging.config
import logging.handlers
import structlog

def configure_logging():
    """Configures structured logging.
    """
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "default": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
            },
            "file": {
                "level": "DEBUG",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": os.path.join(log_directory, "manser-prgen-script.log"),
                "maxBytes": 5242880,
                "backupCount": 3,
            },
        },
        "loggers": {
            "": {
                "handlers": ["default", "file"],
                "level": "DEBUG",
                "propagate": True,
            },
        }
    })

    processors = [
        structlog.stdlib.filter_by_level,
        # structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        # structlog.processors.format_exc_info,

        structlog.processors.TimeStamper(fmt="iso"),
        # structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
        structlog.dev.ConsoleRenderer(colors=True),
    ]

    structlog.configure(
        processors=processors,
        cache_logger_on_first_use=True,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
