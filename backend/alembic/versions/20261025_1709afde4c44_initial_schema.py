"""initial schema

Revision ID: 1709afde4c44
Revises: 
Create Date: 2026-10-25 03:58:56.472604

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1709afde4c44'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('role', sa.Enum('Admin', 'Doctor', 'LabSpecialist', name='role', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('audit_events',
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_events_actor_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index(op.f('ix_audit_events_actor_user_id'), 'audit_events', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_audit_events_occurred_at'), 'audit_events', ['occurred_at'], unique=False)
    op.create_table('patients',
    sa.Column('doctor_id', sa.UUID(), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=False),
    sa.Column('date_of_birth', sa.Date(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_archived', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['doctor_id'], ['users.id'], name=op.f('fk_patients_doctor_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_patients'))
    )
    op.create_index(op.f('ix_patients_doctor_id'), 'patients', ['doctor_id'], unique=False)
    op.create_table('user_tokens',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('purpose', sa.Enum('Invitation', 'PasswordReset', name='token_purpose', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_tokens_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_tokens_token_hash'))
    )
    op.create_index(op.f('ix_user_tokens_user_id'), 'user_tokens', ['user_id'], unique=False)
    op.create_table('cases',
    sa.Column('patient_id', sa.UUID(), nullable=False),
    sa.Column('doctor_id', sa.UUID(), nullable=False),
    sa.Column('examined_at', sa.Date(), nullable=False),
    sa.Column('body_location', sa.String(length=200), nullable=False),
    sa.Column('clinical_description', sa.Text(), nullable=False),
    sa.Column('doctor_assessment', sa.Text(), nullable=True),
    sa.Column('decision', sa.Enum('Close', 'FollowUp', 'Refer', name='case_decision', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('follow_up_date', sa.Date(), nullable=True),
    sa.Column('follow_up_note', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('Open', 'FollowUpPlanned', 'Referred', 'Closed', name='case_status', native_enum=False, create_constraint=True, length=32), server_default='Open', nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['doctor_id'], ['users.id'], name=op.f('fk_cases_doctor_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_cases_patient_id_patients'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cases'))
    )
    op.create_index(op.f('ix_cases_doctor_id'), 'cases', ['doctor_id'], unique=False)
    op.create_index(op.f('ix_cases_patient_id'), 'cases', ['patient_id'], unique=False)
    op.create_index(op.f('ix_cases_status'), 'cases', ['status'], unique=False)
    op.create_table('case_images',
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=64), nullable=False),
    sa.Column('byte_size', sa.BigInteger(), nullable=False),
    sa.Column('checksum_sha256', sa.String(length=64), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_case_images_case_id_cases'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_images')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_case_images_storage_key'))
    )
    op.create_index(op.f('ix_case_images_case_id'), 'case_images', ['case_id'], unique=False)
    op.create_table('ai_analyses',
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('image_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('Queued', 'Running', 'Completed', 'Failed', name='analysis_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('model_name', sa.String(length=64), nullable=False),
    sa.Column('model_sha256', sa.String(length=64), nullable=True),
    sa.Column('preprocessing_version', sa.String(length=64), nullable=False),
    sa.Column('predicted_class_code', sa.String(length=16), nullable=True),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('scores_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('error_message_safe', sa.String(length=500), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_ai_analyses_case_id_cases'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['image_id'], ['case_images.id'], name=op.f('fk_ai_analyses_image_id_case_images'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_analyses'))
    )
    op.create_index(op.f('ix_ai_analyses_case_id'), 'ai_analyses', ['case_id'], unique=False)
    op.create_index('uq_ai_analyses_one_active_per_case', 'ai_analyses', ['case_id'], unique=True, postgresql_where=sa.text("status IN ('Queued', 'Running')"))
    op.create_table('referrals',
    sa.Column('referral_number', sa.String(length=32), nullable=False),
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('doctor_id', sa.UUID(), nullable=False),
    sa.Column('analysis_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Enum('Sent', 'InProgress', 'Completed', name='referral_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['analysis_id'], ['ai_analyses.id'], name=op.f('fk_referrals_analysis_id_ai_analyses'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_referrals_case_id_cases'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['doctor_id'], ['users.id'], name=op.f('fk_referrals_doctor_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_referrals')),
    sa.UniqueConstraint('referral_number', name=op.f('uq_referrals_referral_number'))
    )
    op.create_index(op.f('ix_referrals_case_id'), 'referrals', ['case_id'], unique=False)
    op.create_index(op.f('ix_referrals_doctor_id'), 'referrals', ['doctor_id'], unique=False)
    op.create_index(op.f('ix_referrals_status'), 'referrals', ['status'], unique=False)
    op.create_index('uq_referrals_one_active_per_case', 'referrals', ['case_id'], unique=True, postgresql_where=sa.text("status IN ('Sent', 'InProgress')"))
    op.create_table('xai_artifacts',
    sa.Column('analysis_id', sa.UUID(), nullable=False),
    sa.Column('method', sa.Enum('gradcam', 'gradcam_pp', name='xai_method', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('component_name', sa.String(length=32), nullable=False),
    sa.Column('layer_name', sa.String(length=64), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=True),
    sa.Column('status', sa.Enum('Completed', 'Failed', name='xai_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['analysis_id'], ['ai_analyses.id'], name=op.f('fk_xai_artifacts_analysis_id_ai_analyses'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_xai_artifacts')),
    sa.UniqueConstraint('analysis_id', 'method', 'component_name', name='uq_xai_artifacts_map')
    )
    op.create_index(op.f('ix_xai_artifacts_analysis_id'), 'xai_artifacts', ['analysis_id'], unique=False)
    op.create_table('email_outbox',
    sa.Column('patient_id', sa.UUID(), nullable=True),
    sa.Column('referral_id', sa.UUID(), nullable=True),
    sa.Column('recipient_email', sa.String(length=254), nullable=False),
    sa.Column('template_key', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('Pending', 'Logged', 'Sent', 'Failed', name='email_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_error_safe', sa.String(length=500), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_email_outbox_patient_id_patients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['referral_id'], ['referrals.id'], name=op.f('fk_email_outbox_referral_id_referrals'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_outbox')),
    sa.UniqueConstraint('referral_id', 'template_key', name='uq_email_outbox_referral_template')
    )
    op.create_table('lab_results',
    sa.Column('referral_id', sa.UUID(), nullable=False),
    sa.Column('lab_specialist_id', sa.UUID(), nullable=False),
    sa.Column('lab_accession_number', sa.String(length=64), nullable=True),
    sa.Column('histopathology_diagnosis', sa.Text(), nullable=True),
    sa.Column('histopathology_description', sa.Text(), nullable=True),
    sa.Column('examined_at', sa.Date(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('is_approved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pdf_storage_key', sa.String(length=255), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['lab_specialist_id'], ['users.id'], name=op.f('fk_lab_results_lab_specialist_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['referral_id'], ['referrals.id'], name=op.f('fk_lab_results_referral_id_referrals'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lab_results')),
    sa.UniqueConstraint('lab_accession_number', name=op.f('uq_lab_results_lab_accession_number')),
    sa.UniqueConstraint('referral_id', name=op.f('uq_lab_results_referral_id'))
    )
    op.create_table('notifications',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('referral_id', sa.UUID(), nullable=True),
    sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['referral_id'], ['referrals.id'], name=op.f('fk_notifications_referral_id_referrals'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
    sa.UniqueConstraint('user_id', 'type', 'referral_id', name='uq_notifications_user_type_referral')
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_table('lab_results')
    op.drop_table('email_outbox')
    op.drop_index(op.f('ix_xai_artifacts_analysis_id'), table_name='xai_artifacts')
    op.drop_table('xai_artifacts')
    op.drop_index('uq_referrals_one_active_per_case', table_name='referrals', postgresql_where=sa.text("status IN ('Sent', 'InProgress')"))
    op.drop_index(op.f('ix_referrals_status'), table_name='referrals')
    op.drop_index(op.f('ix_referrals_doctor_id'), table_name='referrals')
    op.drop_index(op.f('ix_referrals_case_id'), table_name='referrals')
    op.drop_table('referrals')
    op.drop_index('uq_ai_analyses_one_active_per_case', table_name='ai_analyses', postgresql_where=sa.text("status IN ('Queued', 'Running')"))
    op.drop_index(op.f('ix_ai_analyses_case_id'), table_name='ai_analyses')
    op.drop_table('ai_analyses')
    op.drop_index(op.f('ix_case_images_case_id'), table_name='case_images')
    op.drop_table('case_images')
    op.drop_index(op.f('ix_cases_status'), table_name='cases')
    op.drop_index(op.f('ix_cases_patient_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_doctor_id'), table_name='cases')
    op.drop_table('cases')
    op.drop_index(op.f('ix_user_tokens_user_id'), table_name='user_tokens')
    op.drop_table('user_tokens')
    op.drop_index(op.f('ix_patients_doctor_id'), table_name='patients')
    op.drop_table('patients')
    op.drop_index(op.f('ix_audit_events_occurred_at'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_actor_user_id'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_table('users')
    # ### end Alembic commands ###
