.PHONY: bootstrap lint-go-build lint-go-test test-py test benchmarks

VENV ?= .venv
PY := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

bootstrap:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements-dev.txt

lint-go-build:
	cd linters/go && go build ./...

lint-go-test:
	cd linters/go && go test ./...

test-py:
	$(PYTEST) -v

test: test-py lint-go-test

benchmarks:
	./benchmarks/run.sh
