from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("autonomous-investment-swarm")
except PackageNotFoundError:
    __version__ = "1.1.0"  # fallback for editable installs

__all__ = ["__version__", "main"]
