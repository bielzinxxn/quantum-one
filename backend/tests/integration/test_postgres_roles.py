"""Mínimo privilégio no Postgres e auditoria append-only."""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import pytest

pytestmark = pytest.mark.integration

APP_ROLES = ("q1_marketdata", "q1_engine", "q1_trader", "q1_accounting", "q1_api")


async def test_every_role_connects_with_q1_search_path(connect: Any) -> None:
    for role in (*APP_ROLES, "q1_migrator"):
        conn = await connect(role)
        try:
            assert await conn.fetchval("SHOW search_path") == "q1"
            assert await conn.fetchval("SHOW TimeZone") == "UTC"
        finally:
            await conn.close()


async def test_migration_applied(connect: Any) -> None:
    conn = await connect("q1_migrator")
    try:
        assert await conn.fetchval("SELECT version_num FROM q1.alembic_version") == "0003"
    finally:
        await conn.close()


@pytest.mark.parametrize("role", APP_ROLES)
async def test_app_roles_cannot_create_objects(connect: Any, role: str) -> None:
    conn = await connect(role)
    try:
        for schema in ("q1", "public"):
            with pytest.raises(
                (asyncpg.InsufficientPrivilegeError, asyncpg.ReadOnlySQLTransactionError)
            ):
                await conn.execute(f"CREATE TABLE {schema}.hack (id int)")
    finally:
        await conn.close()


async def test_audit_log_is_append_only_even_for_owner(connect: Any) -> None:
    trader = await connect("q1_trader")
    owner = await connect("q1_migrator")
    try:
        await trader.execute(
            "INSERT INTO audit_log (actor, action, payload) VALUES ($1, $2, $3::jsonb)",
            "it",
            "integration_test",
            json.dumps({"ok": True}),
        )
        for stmt in (
            "UPDATE audit_log SET actor = 'x'",
            "DELETE FROM audit_log",
            "TRUNCATE audit_log",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await owner.execute(stmt)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await trader.execute("UPDATE audit_log SET actor = 'x'")
    finally:
        await trader.close()
        await owner.close()


async def test_engine_cannot_read_audit_log(connect: Any) -> None:
    conn = await connect("q1_engine")
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.fetch("SELECT * FROM audit_log")
    finally:
        await conn.close()


async def test_api_is_read_only_by_default(connect: Any) -> None:
    conn = await connect("q1_api")
    try:
        assert await conn.fetchval("SELECT count(*) >= 0 FROM audit_log")
        with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
            await conn.execute("INSERT INTO audit_log (actor, action) VALUES ('api', 'x')")
        with pytest.raises(
            (asyncpg.InsufficientPrivilegeError, asyncpg.ReadOnlySQLTransactionError)
        ):
            await conn.execute(
                "INSERT INTO processed_events (consumer, event_id) "
                "VALUES ('api', gen_random_uuid())"
            )
    finally:
        await conn.close()


async def test_processed_events_dedup(connect: Any) -> None:
    conn = await connect("q1_accounting")
    try:
        eid = await conn.fetchval("SELECT gen_random_uuid()")
        await conn.execute(
            "INSERT INTO processed_events (consumer, event_id) VALUES ('it', $1)", eid
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO processed_events (consumer, event_id) VALUES ('it', $1)", eid
            )
    finally:
        await conn.close()
