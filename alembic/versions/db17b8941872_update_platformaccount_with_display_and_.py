"""Update PlatformAccount with display and search names

Revision ID: db17b8941872
Revises: 604458551cc6
Create Date: 2025-07-21 13:08:41.118894

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db17b8941872'
down_revision: Union[str, None] = '604458551cc6'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # --- Создаем новые, правильные таблицы ---
    print("Creating new account tables...")

    op.create_table('platform_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('search_name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('display_name'),
        sa.UniqueConstraint('search_name')
    )
    op.create_table('account_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['platform_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'account_id', name='_user_account_uc')
    )
    print("New tables created successfully.")


def downgrade() -> None:
    # --- Откатываем все обратно ---
    print("Downgrading: Dropping new account tables...")
    op.drop_table('account_assignments')
    op.drop_table('platform_accounts')
    print("Tables dropped. Recreating old ones...")
    
    op.create_table('platform_accounts',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('name', sa.VARCHAR(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_table('account_assignments',
        sa.Column('id', sa.INTEGER(), nullable=False),
        sa.Column('user_id', sa.BIGINT(), nullable=True),
        sa.Column('account_id', sa.INTEGER(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['platform_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'account_id', name='_user_account_uc')
    )
    print("Old tables recreated successfully.")
