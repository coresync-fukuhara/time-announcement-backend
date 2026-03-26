from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect as sqlalchemy_inspect, select
from sqlalchemy.orm import Session


def _ensure_src_on_syspath() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    src_dir = base_dir / "src"
    sys.path.insert(0, str(src_dir))


def _ask_yes_no(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [y/n]: ").strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("y か n を入力してください。")


def _list_wav_files(directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(
        [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".wav"]
    )


def _normalize_track_name_from_wav_file_name(file_name: str) -> str:
    name = file_name.strip()
    if name.lower().endswith(".wav"):
        return name[:-4]
    return name


def _get_or_create_audio_type(
    session: Session,
    AudioTypeMaster: type,
    type_name: str,
) -> object:
    existing = session.scalar(
        select(AudioTypeMaster).where(AudioTypeMaster.name == type_name).limit(1)
    )
    if existing is not None:
        return existing

    created = AudioTypeMaster(name=type_name, description=None)
    session.add(created)
    session.flush()
    return created


def _upsert_track_by_wav(session: Session, WavTrack: type, wav: Path) -> object:
    normalized_name = _normalize_track_name_from_wav_file_name(wav.name)

    track = session.scalar(
        select(WavTrack).where(WavTrack.name == normalized_name).limit(1)
    )
    if track is None:
        track = WavTrack(name=normalized_name, file_path=str(wav))
        session.add(track)
        session.flush()
        return track

    if track.file_path != str(wav):
        track.file_path = str(wav)

    return track


def _register_default_tracks(
    session: Session,
    WavTrack: type,
    type_map: dict[str, object],
    default_dir: Path,
) -> None:
    for wav in _list_wav_files(default_dir):
        track = _upsert_track_by_wav(session, WavTrack, wav)

        assigned = {t.name for t in track.types}
        if "DEFAULT" not in assigned:
            track.types.append(type_map["DEFAULT"])
        if wav.name.lower().endswith("notify.wav") and "NOTIFICATION" not in assigned:
            track.types.append(type_map["NOTIFICATION"])


def _choose_types_for_user_track(available_types: list[str], track_name: str) -> list[str]:
    print(f"\nユーザー楽曲: {track_name}")
    print("割り当てるタイプを選択してください（カンマ区切りで複数可）。")
    for i, type_name in enumerate(available_types, start=1):
        print(f"  {i}. {type_name}")

    while True:
        raw = input("番号を入力: ").strip()
        if not raw:
            print("少なくとも1つ選択してください。")
            continue

        tokens = [part.strip() for part in raw.split(",") if part.strip()]
        try:
            indexes = {int(token) for token in tokens}
        except ValueError:
            print("数値で入力してください。")
            continue

        if any(i < 1 or i > len(available_types) for i in indexes):
            print("範囲外の番号があります。")
            continue

        return [available_types[i - 1] for i in sorted(indexes)]


def _register_user_tracks(
    session: Session,
    WavTrack: type,
    type_map: dict[str, object],
    user_dir: Path,
    available_types: list[str],
) -> None:
    for wav in _list_wav_files(user_dir):
        track_name = _normalize_track_name_from_wav_file_name(wav.name)
        selected = _choose_types_for_user_track(available_types, track_name)

        track = _upsert_track_by_wav(session, WavTrack, wav)
        track.types = [type_map[type_name] for type_name in selected]


def _print_table_state(session: Session, WavTrack: type, AudioTypeMaster: type) -> None:
    print("\n既存テーブル状態")

    audio_types = session.scalars(
        select(AudioTypeMaster).order_by(AudioTypeMaster.name)
    ).all()
    tracks = session.scalars(select(WavTrack).order_by(WavTrack.name)).all()

    print(f"- audio_types: {len(audio_types)} 件")
    for t in audio_types:
        print(f"  - {t.name}")

    print(f"- wav_tracks: {len(tracks)} 件")
    for track in tracks:
        type_names = ", ".join(sorted([t.name for t in track.types])) or "(none)"
        print(f"  - name={track.name}, file_path={track.file_path}, types=[{type_names}]")


def main() -> int:
    _ensure_src_on_syspath()

    from music_db import (
        AudioTypeMaster,
        Base,
        WavTrack,
        create_session_factory,
        create_sqlite_engine,
    )
    from schedules_models import AudioType

    base_dir = Path(__file__).resolve().parents[1]
    db_path = base_dir / "db" / "music.sqlite3"
    default_dir = base_dir / "sounds" / "default"
    user_dir = base_dir / "sounds" / "user"

    engine = create_sqlite_engine(str(db_path))
    inspector = sqlalchemy_inspect(engine)
    required_tables = {"wav_tracks", "audio_types", "track_audio_types"}
    existing_tables = set(inspector.get_table_names())

    needs_recreate = False
    if required_tables.issubset(existing_tables):
        should_rerun = _ask_yes_no(
            "テーブルは既に作成されています。マイグレーションを再実施しますか？"
        )
        if not should_rerun:
            SessionLocal = create_session_factory(engine)
            with SessionLocal() as session:
                _print_table_state(session, WavTrack, AudioTypeMaster)
            return 0
        needs_recreate = True

    if needs_recreate:
        Base.metadata.drop_all(engine)

    Base.metadata.create_all(engine)
    SessionLocal = create_session_factory(engine)

    with SessionLocal() as session:
        available_types = [audio_type.value for audio_type in AudioType]
        type_map: dict[str, object] = {}
        for type_name in available_types:
            type_map[type_name] = _get_or_create_audio_type(
                session, AudioTypeMaster, type_name
            )

        _register_default_tracks(session, WavTrack, type_map, default_dir)
        _register_user_tracks(session, WavTrack, type_map, user_dir, available_types)

        session.commit()
        _print_table_state(session, WavTrack, AudioTypeMaster)

    print(f"\nマイグレーション完了: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
