"""Add the Nextcloud authentication login to users.

Revision ID: 20261006_auth_login
Revises: 20260816_timezones
"""

import sqlalchemy as sa
from alembic import op


revision = "20261006_auth_login"
down_revision = "20260816_timezones"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "nc_auth_login" not in columns:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("nc_auth_login", sa.String(255), nullable=True))


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "nc_auth_login" in columns:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("nc_auth_login")
