"""Add profile_photo_id to user

Revision ID: b5cca10c669c
Revises: c00000000000
Create Date: 2026-07-17 08:55:18.344318

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5cca10c669c'
down_revision = 'c00000000000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user', sa.Column('profile_photo_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('user', 'profile_photo_id')
