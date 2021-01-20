# Makefile for the tl-waste python package

# Prepare CLI for development and/or testing
init:
	python3 -m pipenv install --dev
	python3 -m pipenv shell

# Tests

# The -s argument to pytest disables its by-default capture
# of standard out and standard error (this information is presented
# for failing tests but discarded for passing tests)
PYTEST_ARGS=-s

test_handlers:
	python -m pytest $(PYTEST_ARGS) tests/test_simple_handler.py
	python -m pytest $(PYTEST_ARGS) tests/test_caching_handler.py

test_deployment:
	python -m pytest ${PYTEST_ARGS} tests/test_deployment.py

all_tests: test_handlers test_deployment

# Other quality checks

pep8_check:
	flake8 waste/handler/*.py --count

.PHONY: init test test_handlers test_deployment pep8_check
