from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision = "20250215_fix_timestamp"
down_revision = None  # Replace with the previous migration revision ID
branch_labels = None
depends_on = None

def upgrade():
    """
    Convert the messages.timestamp column from a plain TIMESTAMP
    to TIMESTAMP WITH TIME ZONE (DateTime(timezone=True)).
    This ensures the ORM will correctly produce a Python datetime object
    rather than a string in certain contexts.
    """

    # If needed, parse string data into valid datetimes:
    # op.execute("UPDATE messages SET timestamp = to_timestamp(timestamp, 'YYYY-MM-DD HH24:MI:SS')")

    op.alter_column(
        "messages",
        "timestamp",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.TIMESTAMP(),
        postgresql_using="timestamp::timestamptz"  # for Postgres
    )

def downgrade():
    """
    Revert messages.timestamp to a plain TIMESTAMP without time zone.
    """
    op.alter_column(
        "messages",
        "timestamp",
        type_=sa.TIMESTAMP(),
        existing_type=sa.DateTime(timezone=True),
        postgresql_using="timestamp::timestamp"
    )