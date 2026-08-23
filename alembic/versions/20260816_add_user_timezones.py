"""Add IANA timezone fields to users.

Revision ID: 20260816_timezones
Revises:
"""

import sqlalchemy as sa
from alembic import op


revision = "20260816_timezones"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    with op.batch_alter_table("users") as batch_op:
        if "nc_email" not in columns:
            batch_op.add_column(sa.Column("nc_email", sa.String(255), nullable=True))
        if "nc_time_zone" not in columns:
            batch_op.add_column(sa.Column("nc_time_zone", sa.Integer(), nullable=False,
                                          server_default=sa.text("3")))
        if "nc_timezone" not in columns:
            batch_op.add_column(sa.Column("nc_timezone", sa.String(64), nullable=True))
        if "timezone_override" not in columns:
            batch_op.add_column(sa.Column("timezone_override", sa.String(64), nullable=True))
        if "nc_token" not in columns:
            batch_op.add_column(sa.Column("nc_token", sa.String(100), nullable=True))

    if "nc_time_zone" in columns:
        connection.execute(sa.text(
            "UPDATE users SET timezone_override = CASE "
            "WHEN nc_time_zone = 0 THEN 'Etc/UTC' "
            "WHEN nc_time_zone BETWEEN 1 AND 14 THEN CONCAT('Etc/GMT-', nc_time_zone) "
            "WHEN nc_time_zone BETWEEN -12 AND -1 THEN CONCAT('Etc/GMT+', ABS(nc_time_zone)) "
            "ELSE timezone_override END "
            "WHERE timezone_override IS NULL AND nc_time_zone <> 3"
        ))


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table("users"):
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    with op.batch_alter_table("users") as batch_op:
        if "timezone_override" in columns:
            batch_op.drop_column("timezone_override")
        if "nc_timezone" in columns:
            batch_op.drop_column("nc_timezone")
