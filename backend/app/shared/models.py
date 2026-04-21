import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, BigInteger, Date, ForeignKey, Integer, String, Text, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Archive(Base):
    __tablename__ = "archives"
    __table_args__ = (
        CheckConstraint(
            "analysis_status IN ('pending', 'in_progress', 'completed', 'failed')",
            name="ck_archives_analysis_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    root_path: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)

    # Analysis tracking
    analysis_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    analysis_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Calculated statistics
    file_count: Mapped[int] = mapped_column(nullable=False, default=0)
    directory_count: Mapped[int] = mapped_column(nullable=False, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    files: Mapped[list["File"]] = relationship("File", back_populates="archive", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint(
            "(is_directory = true AND extension IS NULL AND size_bytes IS NULL) OR (is_directory = false)",
            name="ck_files_directory_fields",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=True)

    # File identification
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    full_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(2000), nullable=False)

    # File type and metadata
    is_directory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extension: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # File properties
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Filesystem timestamps
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # System tracking
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    archive: Mapped["Archive"] = relationship("Archive", back_populates="files")
    parent: Mapped["File | None"] = relationship("File", remote_side="File.id", back_populates="children")
    children: Mapped[list["File"]] = relationship("File", back_populates="parent", cascade="all, delete-orphan")
    tika_analysis: Mapped["TikaAnalysis | None"] = relationship("TikaAnalysis", back_populates="file", uselist=False)


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_analysis_tasks_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TikaAnalysis(Base):
    __tablename__ = "tika_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, unique=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tika_parser: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    file: Mapped["File"] = relationship("File", back_populates="tika_analysis")


class AnalysisConfiguration(Base):
    __tablename__ = "analysis_configuration"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    model: Mapped[str] = mapped_column(String(255), nullable=False)


class ArchiveAnalysis(Base):
    __tablename__ = "archive_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    summaries: Mapped[list["Summary"]] = relationship("Summary", back_populates="archive_analysis", cascade="all, delete-orphan")


class Summary(Base):
    __tablename__ = "summary"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archive_analysis.id", ondelete="CASCADE"), nullable=False)
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)

    archive_analysis: Mapped["ArchiveAnalysis"] = relationship("ArchiveAnalysis", back_populates="summaries")
