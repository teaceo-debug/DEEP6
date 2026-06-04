.PHONY: test lint typecheck run run-dry

test:
	pytest tests_v2/

lint:
	python -m compileall deep6v2 tests_v2

typecheck:
	python -m py_compile deep6v2/__init__.py deep6v2/__main__.py

run:
	python -m deep6v2

run-dry:
	python -m deep6v2
