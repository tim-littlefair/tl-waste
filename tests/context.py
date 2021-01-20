import logging
import os
import sys

# Set up path so that tests can find SUT package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set up standadr logging config
_logger = logging.getLogger()
print()
if _logger is None:
    _logger = logging.basicConfig()
    print("Using new logger")
else:
    print("Using existing logger")
_logger.setLevel(logging.DEBUG)
_logging_handler = logging.StreamHandler()
_logging_handler.setFormatter(logging.Formatter("%(levelname)-10s %(message)s"))
_logger.addHandler(_logging_handler)


