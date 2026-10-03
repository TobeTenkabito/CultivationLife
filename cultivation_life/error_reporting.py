"""Bounded local diagnostics for unexpected request failures, including windowed builds."""
import logging
import threading
from logging.handlers import RotatingFileHandler


LOGGER = logging.getLogger('cultivation_life.server')
_log_lock = threading.Lock()


def report_internal_error(root, request_id, method, operation, error):
    # Do not include the request body, full URL, player name or save contents.
    record = LOGGER.makeRecord(
        LOGGER.name, logging.ERROR, __file__, 0,
        'Unhandled request request_id=%s method=%s operation=%s',
        (request_id, method, operation), (type(error), error, error.__traceback__),
    )
    LOGGER.handle(record)
    try:
        with _log_lock:
            directory = root / 'data' / 'logs'
            directory.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                directory / 'server-errors.log', maxBytes=1_000_000,
                backupCount=3, encoding='utf-8',
            )
            try:
                handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
                handler.handle(record)
            finally:
                handler.close()
    except OSError:
        # Diagnostics must not prevent the client from receiving its error response.
        LOGGER.warning('Could not write the local server error log')
