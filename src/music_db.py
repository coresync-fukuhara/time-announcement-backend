from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, selectinload, sessionmaker


class Base(DeclarativeBase):
    pass


class TrackAudioType(Base):
    __tablename__ = "track_audio_types"
    __table_args__ = (UniqueConstraint("track_id", "audio_type_id", name="uq_track_audio_type"),)

    track_id: Mapped[int] = mapped_column(
        ForeignKey("wav_tracks.id", ondelete="CASCADE"), primary_key=True
    )
    audio_type_id: Mapped[int] = mapped_column(
        ForeignKey("audio_types.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class WavTrack(Base):
    __tablename__ = "wav_tracks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    types: Mapped[list[AudioTypeMaster]] = relationship(
        secondary="track_audio_types", back_populates="tracks", lazy="selectin"
    )


class AudioTypeMaster(Base):
    __tablename__ = "audio_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    tracks: Mapped[list[WavTrack]] = relationship(
        secondary="track_audio_types", back_populates="types", lazy="selectin"
    )


def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_sqlite_engine(db_path: str = "db/music.sqlite3") -> Engine:
    target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{target}", future=True)
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def get_track_by_name(session: Session, track_name: str) -> WavTrack | None:
    stmt = (
        select(WavTrack)
        .where(WavTrack.name == track_name)
        .options(selectinload(WavTrack.types))
        .limit(1)
    )
    return session.scalar(stmt)


def get_random_track_by_type(
    session: Session,
    type_name: str,
    exclude_track_names: Sequence[str] | None = None,
) -> WavTrack | None:
    stmt = (
        select(WavTrack)
        .join(WavTrack.types)
        .where(AudioTypeMaster.name == type_name)
        .options(selectinload(WavTrack.types))
    )

    if exclude_track_names:
        stmt = stmt.where(~WavTrack.name.in_(list(exclude_track_names)))

    stmt = stmt.order_by(func.random()).limit(1)
    return session.scalar(stmt)
