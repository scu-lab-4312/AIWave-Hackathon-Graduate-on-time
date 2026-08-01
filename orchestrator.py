"""Compatibility entrypoint; canonical code lives in apps/orchestrator."""

from apps.orchestrator.main import app, invoke, process_turn

__all__ = ["app", "invoke", "process_turn"]


if __name__ == "__main__":
    app.run()
