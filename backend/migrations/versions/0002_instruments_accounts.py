"""Instrumentos (exchangeInfo) e snapshots de conta/saldo lidos da exchange.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE_STATEMENTS = (
    """
    CREATE TABLE q1.instruments (
        symbol         text PRIMARY KEY,
        base           text NOT NULL,
        quote          text NOT NULL,
        status         text NOT NULL,
        tick_size      numeric(38,18) NOT NULL,
        min_price      numeric(38,18) NOT NULL,
        max_price      numeric(38,18) NOT NULL,
        step_size      numeric(38,18) NOT NULL,
        min_qty        numeric(38,18) NOT NULL,
        max_qty        numeric(38,18) NOT NULL,
        min_notional   numeric(38,18) NOT NULL,
        max_notional   numeric(38,18),
        order_types    text[] NOT NULL,
        spot_allowed   boolean NOT NULL,
        oco_allowed    boolean NOT NULL,
        first_seen_at  timestamptz NOT NULL DEFAULT now(),
        last_seen_at   timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX instruments_quote_status_idx ON q1.instruments (quote, status)",
    """
    CREATE TABLE q1.account_snapshots (
        id                bigserial PRIMARY KEY,
        taken_at          timestamptz NOT NULL,
        source            text NOT NULL CHECK (source IN ('exchange')),
        account_type      text NOT NULL,
        can_trade         boolean NOT NULL,
        maker_commission  numeric(38,18) NOT NULL,
        taker_commission  numeric(38,18) NOT NULL,
        open_orders       integer NOT NULL CHECK (open_orders >= 0)
    )
    """,
    "CREATE INDEX account_snapshots_taken_at_idx ON q1.account_snapshots (taken_at)",
    """
    CREATE TABLE q1.balance_snapshots (
        snapshot_id  bigint NOT NULL REFERENCES q1.account_snapshots(id),
        asset        text NOT NULL,
        free         numeric(38,18) NOT NULL CHECK (free >= 0),
        locked       numeric(38,18) NOT NULL CHECK (locked >= 0),
        PRIMARY KEY (snapshot_id, asset)
    )
    """,
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)
    op.execute("GRANT SELECT, INSERT, UPDATE ON q1.instruments TO q1_marketdata")
    for role in ("q1_engine", "q1_trader", "q1_accounting", "q1_api"):
        op.execute(f"GRANT SELECT ON q1.instruments TO {role}")
    op.execute("GRANT SELECT, INSERT ON q1.account_snapshots, q1.balance_snapshots TO q1_trader")
    op.execute("GRANT USAGE ON SEQUENCE q1.account_snapshots_id_seq TO q1_trader")
    for role in ("q1_accounting", "q1_api"):
        op.execute(f"GRANT SELECT ON q1.account_snapshots, q1.balance_snapshots TO {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS q1.balance_snapshots")
    op.execute("DROP TABLE IF EXISTS q1.account_snapshots")
    op.execute("DROP TABLE IF EXISTS q1.instruments")
