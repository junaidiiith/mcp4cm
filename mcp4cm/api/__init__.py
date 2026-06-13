"""Flask API package for MCP4CM web workflows."""

from mcp4cm.api.app import create_app, main, run

__all__ = ["create_app", "main", "run"]
