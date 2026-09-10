"""Optional dependency loaders for database and organization-private HDLF collection."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any, Callable


@dataclass(frozen=True)
class DatabaseAdapter:
    """SQLAlchemy objects used only by database-backed collection."""

    create_async_engine: Callable[..., Any]
    text: Callable[..., Any]


@dataclass(frozen=True)
class HdlfAdapter:
    """Organization-private HDLF classes used only by direct HDLF modes."""

    client: type[Any]
    connection_params: type[Any]
    settings: type[Any]


@cache
def load_database_adapter() -> DatabaseAdapter:
    """Load SQLAlchemy only when database-backed collection is requested."""
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError as exc:
        raise RuntimeError(
            "Database collection requires the collection dependency group. "
            "Install it with: uv sync --locked --extra collection"
        ) from exc
    return DatabaseAdapter(create_async_engine=create_async_engine, text=text)


@cache
def load_hdlf_adapter() -> HdlfAdapter:
    """Load the private HDLF client only when direct HDLF access is requested."""
    try:
        from fl_shared.hdlf_client.client import HdlfClient, HdlfConnectionParams
        from fl_shared.hdlf_client.config import Settings as HdlfSettings
    except ImportError as exc:
        raise RuntimeError(
            "Direct HDLF collection requires the organization-private fl_shared package. "
            "Use GitHub comment collection or --hdlf-via-api when fl_shared is unavailable."
        ) from exc
    return HdlfAdapter(client=HdlfClient, connection_params=HdlfConnectionParams, settings=HdlfSettings)
