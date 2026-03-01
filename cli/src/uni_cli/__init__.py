"""uni-cli: Token-efficient CLI for LLM agents to control Unity Editor."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("uni-cli")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
