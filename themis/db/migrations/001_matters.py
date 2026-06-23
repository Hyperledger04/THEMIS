"""Alembic migration: V3.1 — canonical matter store.

Applies on top of the workspace schema (001_workspace.sql) which already
created the matters table with TEXT columns. This migration:

  1. Creates firms table (tenant identity)
  2. Creates lawyers table (lawyer identity within firm)
  3. Inserts a 'default' firm and 'default' lawyer for legacy workspace rows
  4. Adds V3 columns to matters: lawyer_id, parties, next_action, priority,
     deadline, summary, key_facts, statutes_cited, risk_score
  5. Backfills lawyer_id = user_id for existing rows
  6. Applies Postgres Row-Level Security (RLS) policy

Run with: alembic upgrade head
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "001_v3_matters"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. firms — tenant identity
    # ------------------------------------------------------------------
    op.create_table(
        "firms",
        sa.Column("firm_id", sa.String, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # 2. lawyers — lawyer identity within a firm
    # ------------------------------------------------------------------
    op.create_table(
        "lawyers",
        sa.Column("lawyer_id", sa.String, primary_key=True),
        sa.Column(
            "firm_id",
            sa.String,
            sa.ForeignKey("firms.firm_id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # 3. Seed default firm + lawyer so existing workspace rows stay valid
    # ------------------------------------------------------------------
    op.execute(
        "INSERT INTO firms (firm_id, name) VALUES ('default', 'Default Firm') "
        "ON CONFLICT (firm_id) DO NOTHING"
    )
    op.execute(
        "INSERT INTO lawyers (lawyer_id, firm_id, name) "
        "VALUES ('default', 'default', 'Default Lawyer') "
        "ON CONFLICT (lawyer_id) DO NOTHING"
    )

    # ------------------------------------------------------------------
    # 4. Add V3 columns to the existing matters table
    # ------------------------------------------------------------------
    op.add_column("matters", sa.Column("lawyer_id", sa.String, nullable=True))
    op.add_column("matters", sa.Column("parties", JSONB, nullable=True))
    op.add_column(
        "matters",
        sa.Column("next_action", JSONB, nullable=True),
    )
    op.add_column(
        "matters",
        sa.Column("priority", sa.Integer, server_default="5", nullable=False),
    )
    op.add_column("matters", sa.Column("deadline", sa.Date, nullable=True))
    op.add_column("matters", sa.Column("summary", sa.Text, nullable=True))
    op.add_column("matters", sa.Column("key_facts", JSONB, nullable=True))
    op.add_column("matters", sa.Column("statutes_cited", JSONB, nullable=True))
    op.add_column("matters", sa.Column("risk_score", sa.Float, nullable=True))

    # ------------------------------------------------------------------
    # 5. Backfill lawyer_id = user_id for legacy rows, then FK-scope them
    # ------------------------------------------------------------------
    op.execute("UPDATE matters SET lawyer_id = user_id WHERE lawyer_id IS NULL")
    op.execute("UPDATE matters SET firm_id = 'default' WHERE firm_id IS NULL OR firm_id = ''")

    # Add FK constraints now that data is clean
    op.create_foreign_key(
        "fk_matters_firm_id", "matters", "firms", ["firm_id"], ["firm_id"]
    )
    op.create_foreign_key(
        "fk_matters_lawyer_id", "matters", "lawyers", ["lawyer_id"], ["lawyer_id"]
    )

    # ------------------------------------------------------------------
    # 6. Row-Level Security — every query auto-scoped to app.firm_id
    #
    # WHY: ALTER TABLE … ENABLE ROW LEVEL SECURITY cannot be expressed via
    # Alembic's op.* helpers — those only cover DDL supported by SA Core.
    # op.execute() drops to raw SQL which is perfectly safe here.
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE matters ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE matters FORCE ROW LEVEL SECURITY")

    # The policy fires on SELECT, INSERT, UPDATE, DELETE — covers all paths.
    # current_setting('app.firm_id') is set by scoped_session() in engine.py.
    op.execute(
        """
        CREATE POLICY firm_isolation ON matters
            USING (firm_id = current_setting('app.firm_id')::TEXT)
        """
    )

    # Superuser bypass for migrations and admin tools (does not affect app queries).
    op.execute("ALTER TABLE matters OWNER TO themis")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS firm_isolation ON matters")
    op.execute("ALTER TABLE matters DISABLE ROW LEVEL SECURITY")

    op.drop_constraint("fk_matters_lawyer_id", "matters", type_="foreignkey")
    op.drop_constraint("fk_matters_firm_id", "matters", type_="foreignkey")

    for col in [
        "lawyer_id", "parties", "next_action", "priority",
        "deadline", "summary", "key_facts", "statutes_cited", "risk_score",
    ]:
        op.drop_column("matters", col)

    op.drop_table("lawyers")
    op.drop_table("firms")
