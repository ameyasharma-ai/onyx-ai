content = """\"\"\"Add Chatterbox voice fields to Persona

Revision ID: 2408050fbf1f
Revises: 979aadfa20ea
Create Date: 2026-07-15 13:19:00.000000

\"\"\"
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import fastapi_users_db_sqlalchemy

# revision identifiers, used by Alembic.
revision = '2408050fbf1f'
down_revision = '979aadfa20ea'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('persona', sa.Column('reference_audio_id', sa.String(), nullable=True))
    op.add_column('persona', sa.Column('voice_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('persona', sa.Column('voice_status', sa.String(), nullable=True))
    op.add_column('persona', sa.Column('voice_last_updated', sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column('persona', 'voice_last_updated')
    op.drop_column('persona', 'voice_status')
    op.drop_column('persona', 'voice_metadata')
    op.drop_column('persona', 'reference_audio_id')
"""
with open('/app/alembic/versions/2408050fbf1f_add_chatterbox_voice_fields_to_persona.py', 'w') as f:
    f.write(content)
