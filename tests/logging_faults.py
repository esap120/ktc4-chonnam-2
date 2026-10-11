"""Real logging filters/handlers, with no DB or transaction replacements."""

import logging


def install_logging_fault(logger, sink, predicate, error=None):
    seen = []
    failure = error if error is not None else ValueError("secret /private/logger transport payload")

    def fail(record):
        if predicate(record.runtime_event):
            seen.append(record.runtime_event)
            raise failure
        return True

    class BrokenHandler(logging.Handler):
        def emit(self, record):
            fail(record)

    fault = fail if sink == "filter" else BrokenHandler()
    if sink == "filter":
        logger.addFilter(fault)
    else:
        logger.addHandler(fault)

    def remove():
        if sink == "filter":
            logger.removeFilter(fault)
        else:
            logger.removeHandler(fault)
            fault.close()

    return seen, remove
