"""Velas fechadas e snapshots do Market Scanner.

Tabela simples + BRIN em open_time (ADR-009 §7); particionamento quando o volume justificar.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE_STATEMENTS = (
    """
    CREATE TABLE q1.candles (
        symbol        text NOT NULL,
        timeframe     text NOT NULL,
        open_time     timestamptz NOT NULL,
        open          numeric(38,18) NOT NULL,
        high          numeric(38,18) NOT NULL,
        low           numeric(38,18) NOT NULL,
        close         numeric(38,18) NOT NULL,
        volume        numeric(38,18) NOT NULL,
        quote_volume  numeric(38,18) NOT NULL,
        trades        integer NOT NULL,
        source        text NOT NULL CHECK (source IN ('stream', 'rest')),
        inserted_at   timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (symbol, timeframe, open_time),
        CHECK (high >= low AND high >= open AND high >= close AND low <= open AND low <= close)
    )
    """,
    "CREATE INDEX candles_open_time_brin ON q1.candles USING brin (open_time)",
    """
    CREATE TABLE q1.scanner_snapshots (
        ts             timestamptz NOT NULL,
        symbol         text NOT NULL,
        stale          boolean NOT NULL,
        last_close     numeric(38,18),
        spread_bps     double precision,
        depth_bid_1pct double precision,
        depth_ask_1pct double precision,
        depth_truncated boolean NOT NULL,
        slippage_buy_bps double precision,
        slippage_sell_bps double precision,
        ret_5m         double precision,
        ret_60m        double precision,
        return_z_1m    double precision,
        rel_volume_1m  double precision,
        realized_vol_1h double precision,
        flags          text[] NOT NULL,
        PRIMARY KEY (symbol, ts)
    )
    """,
    "CREATE INDEX scanner_snapshots_ts_brin ON q1.scanner_snapshots USING brin (ts)",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)
    op.execute("GRANT SELECT, INSERT, UPDATE ON q1.candles TO q1_marketdata")
    op.execute("GRANT SELECT, INSERT ON q1.scanner_snapshots TO q1_marketdata")
    for role in ("q1_engine", "q1_trader", "q1_accounting", "q1_api"):
        op.execute(f"GRANT SELECT ON q1.candles TO {role}")
    for role in ("q1_engine", "q1_api"):
        op.execute(f"GRANT SELECT ON q1.scanner_snapshots TO {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS q1.scanner_snapshots")
    op.execute("DROP TABLE IF EXISTS q1.candles")
