"""Baseline: tabelas de infraestrutura (auditoria e deduplicação de eventos) e permissões.

- audit_log é append-only: trigger bloqueia UPDATE/DELETE/TRUNCATE inclusive para o dono.
  O hash encadeado (prev_hash/hash) será preenchido pela aplicação na Fase 12.
- processed_events: deduplicação dos consumidores de Redis Streams (ADR-003).

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLES = ("q1_marketdata", "q1_engine", "q1_trader", "q1_accounting", "q1_api")
CONSUMER_ROLES = ("q1_engine", "q1_trader", "q1_accounting")


UPGRADE_STATEMENTS = (
    """
    CREATE TABLE q1.audit_log (
        id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        ts         timestamptz NOT NULL DEFAULT now(),
        actor      text NOT NULL CHECK (length(actor) BETWEEN 1 AND 128),
        action     text NOT NULL CHECK (length(action) BETWEEN 1 AND 128),
        payload    jsonb NOT NULL DEFAULT '{}'::jsonb,
        prev_hash  bytea,
        hash       bytea
    )
    """,
    "CREATE INDEX audit_log_ts_idx ON q1.audit_log (ts)",
    """
    CREATE FUNCTION q1.forbid_mutation() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'tabela % é append-only', TG_TABLE_NAME
            USING ERRCODE = 'insufficient_privilege';
    END;
    $$
    """,
    """
    CREATE TRIGGER audit_log_no_update_delete
        BEFORE UPDATE OR DELETE ON q1.audit_log
        FOR EACH ROW EXECUTE FUNCTION q1.forbid_mutation()
    """,
    """
    CREATE TRIGGER audit_log_no_truncate
        BEFORE TRUNCATE ON q1.audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION q1.forbid_mutation()
    """,
    """
    CREATE TABLE q1.processed_events (
        consumer      text NOT NULL,
        event_id      uuid NOT NULL,
        processed_at  timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (consumer, event_id)
    )
    """,
)


def upgrade() -> None:
    # asyncpg executa um comando por chamada
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)
    for role in APP_ROLES:
        op.execute(f"GRANT INSERT ON q1.audit_log TO {role}")
    op.execute("GRANT SELECT ON q1.audit_log TO q1_api")
    for role in CONSUMER_ROLES:
        op.execute(f"GRANT SELECT, INSERT ON q1.processed_events TO {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS q1.processed_events")
    op.execute("DROP TABLE IF EXISTS q1.audit_log")
    op.execute("DROP FUNCTION IF EXISTS q1.forbid_mutation()")
