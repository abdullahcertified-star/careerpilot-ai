"""create saved searches, scheduled scan runs, and notifications

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-25 11:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for Phase 8."""
    op.create_table(
        'saved_searches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('role', sa.String(length=150), nullable=True),
        sa.Column('keywords', sa.JSON(), nullable=False),
        sa.Column('location', sa.String(length=150), nullable=True),
        sa.Column('work_mode', sa.String(length=50), nullable=False, server_default='any'),
        sa.Column('employment_type', sa.String(length=50), nullable=False, server_default='any'),
        sa.Column('min_match_score', sa.Float(), nullable=False, server_default='70.0'),
        sa.Column('interval_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('provider_id', sa.String(length=50), nullable=False, server_default='all'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('in_app_notifications', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('email_notifications', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_runs_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_saved_searches_id'), 'saved_searches', ['id'], unique=False)
    op.create_index(op.f('ix_saved_searches_user_id'), 'saved_searches', ['user_id'], unique=False)
    op.create_index(op.f('ix_saved_searches_is_active'), 'saved_searches', ['is_active'], unique=False)
    op.create_index(op.f('ix_saved_searches_next_run_at'), 'saved_searches', ['next_run_at'], unique=False)

    op.create_table(
        'scheduled_scan_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('saved_search_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('jobs_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('new_jobs_ingested', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('high_matches_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('run_metadata', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['saved_search_id'], ['saved_searches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_scheduled_scan_runs_idempotency_key')
    )
    op.create_index(op.f('ix_scheduled_scan_runs_id'), 'scheduled_scan_runs', ['id'], unique=False)
    op.create_index(op.f('ix_scheduled_scan_runs_saved_search_id'), 'scheduled_scan_runs', ['saved_search_id'], unique=False)
    op.create_index(op.f('ix_scheduled_scan_runs_status'), 'scheduled_scan_runs', ['status'], unique=False)
    op.create_index(op.f('ix_scheduled_scan_runs_idempotency_key'), 'scheduled_scan_runs', ['idempotency_key'], unique=True)

    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_sent', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_id'), 'notifications', ['id'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_index(op.f('ix_notifications_type'), 'notifications', ['type'], unique=False)
    op.create_index(op.f('ix_notifications_is_read'), 'notifications', ['is_read'], unique=False)
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema for Phase 8."""
    op.drop_table('notifications')
    op.drop_table('scheduled_scan_runs')
    op.drop_table('saved_searches')
