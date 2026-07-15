"""Add Persona Library Fields

Revision ID: 979aadfa20ea
Revises: ffc707a226b4
Create Date: 2026-07-15 05:14:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import fastapi_users_db_sqlalchemy

# revision identifiers, used by Alembic.
revision = '979aadfa20ea'
down_revision = 'c7d1f0a4b8e2'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add new columns to persona
    op.add_column('persona', sa.Column('slug', sa.String(), nullable=True))
    op.add_column('persona', sa.Column('long_description', sa.String(), nullable=True))
    op.add_column('persona', sa.Column('banner_image_id', sa.String(), nullable=True))
    op.add_column('persona', sa.Column('voice_id', sa.String(), nullable=True))
    op.add_column('persona', sa.Column('temperature', sa.Float(), nullable=True))
    op.add_column('persona', sa.Column('category', sa.String(), nullable=True))
    op.add_column('persona', sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('persona', sa.Column('rating_average', sa.Float(), server_default='0.0', nullable=False))
    op.add_column('persona', sa.Column('rating_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('persona', sa.Column('favorite_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('persona', sa.Column('chat_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('persona', sa.Column('time_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('persona', sa.Column('time_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    
    op.create_index(op.f('ix_persona_slug'), 'persona', ['slug'], unique=True)

    # Create persona_favorite table
    op.create_table('persona_favorite',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('time_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['persona_id'], ['persona.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'persona_id', name='uq_persona_favorite_user_persona')
    )

    # Create persona_rating table
    op.create_table('persona_rating',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('time_created', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='ck_persona_rating_range'),
        sa.ForeignKeyConstraint(['persona_id'], ['persona.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'persona_id', name='uq_persona_rating_user_persona')
    )

def downgrade() -> None:
    op.drop_table('persona_rating')
    op.drop_table('persona_favorite')
    
    op.drop_index(op.f('ix_persona_slug'), table_name='persona')
    op.drop_column('persona', 'time_updated')
    op.drop_column('persona', 'time_created')
    op.drop_column('persona', 'chat_count')
    op.drop_column('persona', 'favorite_count')
    op.drop_column('persona', 'rating_count')
    op.drop_column('persona', 'rating_average')
    op.drop_column('persona', 'tags')
    op.drop_column('persona', 'category')
    op.drop_column('persona', 'temperature')
    op.drop_column('persona', 'voice_id')
    op.drop_column('persona', 'banner_image_id')
    op.drop_column('persona', 'long_description')
    op.drop_column('persona', 'slug')
