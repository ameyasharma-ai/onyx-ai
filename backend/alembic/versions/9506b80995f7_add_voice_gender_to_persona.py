"""add_voice_gender_to_persona

Revision ID: 9506b80995f7
Revises: 2408050fbf1f
Create Date: 2026-07-16 06:54:55.471418

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9506b80995f7'
down_revision = '2408050fbf1f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('persona', sa.Column('voice_gender', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('persona', 'voice_gender')
