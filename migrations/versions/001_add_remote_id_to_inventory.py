"""Add remote_id to InventoryItem

Revision ID: add_remote_id_to_inventory
Revises: 
Create Date: 2025-09-22 07:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_remote_id_to_inventory'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add remote_id column to inventory_items table
    with op.batch_alter_table('inventory_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('remote_id', sa.String(36), nullable=True))


def downgrade():
    # Remove remote_id column from inventory_items table
    with op.batch_alter_table('inventory_items', schema=None) as batch_op:
        batch_op.drop_column('remote_id')
