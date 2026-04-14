.PHONY: up down status logs health

up:
	@./scripts/deep6_up.sh --demo

down:
	@./scripts/deep6_down.sh

status:
	@./scripts/deep6_status.sh

logs:
	@tail -f logs/*.log

health:
	@.venv/bin/python scripts/deep6_healthcheck.py
