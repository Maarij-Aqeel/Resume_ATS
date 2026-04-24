"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-24 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "resumes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("original_filename", sa.Text, nullable=False),
        sa.Column("file_type", sa.String(10)),
        sa.Column("file_size_bytes", sa.Integer),
        sa.Column("raw_text", sa.Text),
        sa.Column("parsed_data", JSONB),
        sa.Column("confidence_score", sa.Numeric(4, 3)),
        sa.Column("extractor_used", sa.String(50)),
        sa.Column("ocr_used", sa.Boolean, server_default=sa.text("false")),
        sa.Column("parse_status", sa.String(20), server_default="pending"),
        sa.Column("parse_attempts", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("embedding", Vector(384)),
        sa.Column("parse_time_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "job_descriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("company", sa.Text),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("required_skills", JSONB),
        sa.Column("required_years", sa.Integer),
        sa.Column("embedding", Vector(384)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "match_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("resume_id", UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="CASCADE")),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("job_descriptions.id", ondelete="CASCADE")),
        sa.Column("total_score", sa.Numeric(5, 2)),
        sa.Column("score_breakdown", JSONB),
        sa.Column("missing_skills", JSONB),
        sa.Column("matching_skills", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "parse_failures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("resume_id", UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="CASCADE")),
        sa.Column("failure_stage", sa.String(50)),
        sa.Column("error_details", sa.Text),
        sa.Column("raw_text_sample", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # IVFFlat index for fast cosine ANN on embeddings
    op.execute(
        "CREATE INDEX IF NOT EXISTS resumes_embedding_cosine_idx "
        "ON resumes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS jobs_embedding_cosine_idx "
        "ON job_descriptions USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_index("idx_resumes_status", "resumes", ["parse_status"])
    op.create_index("idx_resumes_confidence", "resumes", ["confidence_score"])
    op.create_index("idx_resumes_created", "resumes", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_resumes_created", table_name="resumes")
    op.drop_index("idx_resumes_confidence", table_name="resumes")
    op.drop_index("idx_resumes_status", table_name="resumes")
    op.execute("DROP INDEX IF EXISTS jobs_embedding_cosine_idx")
    op.execute("DROP INDEX IF EXISTS resumes_embedding_cosine_idx")
    op.drop_table("parse_failures")
    op.drop_table("match_results")
    op.drop_table("job_descriptions")
    op.drop_table("resumes")
