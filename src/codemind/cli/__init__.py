"""CLI module for CodeMind."""

def __getattr__(name: str):
    if name == "app":
        from codemind.cli.main import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["app"]
