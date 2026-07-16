"""Add persona brain fields

Revision ID: c00000000000
Revises: 9506b80995f7
Create Date: 2026-07-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c00000000000'
down_revision = '9506b80995f7'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('persona', sa.Column('personality_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('persona', sa.Column('speaking_style_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('persona', sa.Column('voice_profile_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('persona', sa.Column('compiled_persona_profile', sa.String(), nullable=True))
    op.add_column('persona', sa.Column('compiled_voice_profile', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('persona', sa.Column('compilation_timestamp', sa.DateTime(timezone=True), nullable=True))
    op.add_column('persona', sa.Column('version', sa.Integer(), server_default='1', nullable=False))

def downgrade() -> None:
    op.drop_column('persona', 'version')
    op.drop_column('persona', 'compilation_timestamp')
    op.drop_column('persona', 'compiled_voice_profile')
    op.drop_column('persona', 'compiled_persona_profile')
    op.drop_column('persona', 'voice_profile_config')
    op.drop_column('persona', 'speaking_style_config')
    op.drop_column('persona', 'personality_config')
