# ── Book Quiz — Quick Commands ────────────────────────────────────
# All targets delegate to ./dev for consistency.
# If you have ./dev, prefer: ./dev <command>
# If you prefer make:  make setup, make up, make test, etc.

.PHONY: setup up down test lint format clean help

setup:
	@./dev setup

up:
	@./dev up

down:
	@./dev down

test:
	@./dev test

lint:
	@./dev lint

format:
	@./dev format

db-migrate:
	@./dev db-migrate

db-reset:
	@./dev db-reset

clean:
	@./dev clean

doctor:
	@./dev doctor

help:
	@echo "Book Quiz — Development Commands"
	@echo ""
	@echo "  make setup       First-time environment setup"
	@echo "  make up          Start full stack"
	@echo "  make down        Stop all services"
	@echo "  make test        Run all tests"
	@echo "  make lint        Run linters"
	@echo "  make format      Auto-format code"
	@echo "  make db-migrate  Run database migrations"
	@echo "  make clean       Remove build artifacts"
	@echo "  make doctor      Diagnose issues"
	@echo ""
	@echo "  Or use ./dev directly:  ./dev setup, ./dev up, ./dev test, ..."
