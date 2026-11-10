"""Vercel entry point: exposes the ASGI app."""

from delivery_mcp.server import app

__all__ = ["app"]
