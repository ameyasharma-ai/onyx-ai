"""add_voice_gender_to_persona

Revision ID: 861dec209b22
Revises: d4e7a92c1b38
Create Date: 2026-07-16 06:55:38.727798

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '861dec209b22'
down_revision = 'd4e7a92c1b38'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('persona', sa.Column('voice_gender', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('persona', 'voice_gender')
