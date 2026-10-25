"""create application submission attempts and package fields

Revision ID: a1b2c3d4e5f6
Revises: fd53dcf0c9a2
Create Date: 2026-10-25 10:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fd53dcf0c9a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for Phase 7."""
    op.add_column('job_applications', sa.Column('form_answers', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('job_applications', sa.Column('approval_snapshot', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('job_applications', sa.Column('approved_package_hash', sa.String(length=128), nullable=True))
    op.create_index(op.f('ix_job_applications_approved_package_hash'), 'job_applications', ['approved_package_hash'], unique=False)

    op.create_table(
        'application_submission_attempts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('submission_key', sa.String(length=128), nullable=False),
        sa.Column('actor_id', sa.String(length=100), nullable=False),
        sa.Column('provider_id', sa.String(length=64), nullable=False),
        sa.Column('submission_method', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=64), nullable=False),
        sa.Column('package_hash', sa.String(length=128), nullable=False),
        sa.Column('resume_version_id', sa.Integer(), nullable=True),
        sa.Column('cover_letter_version_id', sa.Integer(), nullable=True),
        sa.Column('form_answers_snapshot', sa.JSON(), nullable=False),
        sa.Column('receipt_reference', sa.String(length=255), nullable=True),
        sa.Column('response_payload', sa.JSON(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('blind_resubmission_prevented', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['job_applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('submission_key', name='uq_submission_attempts_submission_key'),
    )
    op.create_index(op.f('ix_application_submission_attempts_application_id'), 'application_submission_attempts', ['application_id'], unique=False)
    op.create_index(op.f('ix_application_submission_attempts_id'), 'application_submission_attempts', ['id'], unique=False)
    op.create_index(op.f('ix_application_submission_attempts_provider_id'), 'application_submission_attempts', ['provider_id'], unique=False)
    op.create_index(op.f('ix_application_submission_attempts_status'), 'application_submission_attempts', ['status'], unique=False)
    op.create_index(op.f('ix_application_submission_attempts_submission_key'), 'application_submission_attempts', ['submission_key'], unique=True)
    op.create_index(op.f('ix_application_submission_attempts_user_id'), 'application_submission_attempts', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_application_submission_attempts_user_id'), table_name='application_submission_attempts')
    op.drop_index(op.f('ix_application_submission_attempts_submission_key'), table_name='application_submission_attempts')
    op.drop_index(op.f('ix_application_submission_attempts_status'), table_name='application_submission_attempts')
    op.drop_index(op.f('ix_application_submission_attempts_provider_id'), table_name='application_submission_attempts')
    op.drop_index(op.f('ix_application_submission_attempts_id'), table_name='application_submission_attempts')
    op.drop_index(op.f('ix_application_submission_attempts_application_id'), table_name='application_submission_attempts')
    op.drop_table('application_submission_attempts')

    op.drop_index(op.f('ix_job_applications_approved_package_hash'), table_name='job_applications')
    op.drop_column('job_applications', 'approved_package_hash')
    op.drop_column('job_applications', 'approval_snapshot')
    op.drop_column('job_applications', 'form_answers')
