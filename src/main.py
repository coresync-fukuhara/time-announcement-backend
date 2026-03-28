import datetime
import json
import os
import random
from collections.abc import Sequence
from typing import Any, Optional
from zoneinfo import ZoneInfo

import jpholiday
from scipy.io import wavfile
import sounddevice as sd

from music_db import (
    create_session_factory,
    create_sqlite_engine,
    get_random_track_by_type,
    get_track_by_name,
)
from schedules_models import AudioType, MinuteSettings, WeeklySchedule

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE_PATH = os.path.join(BASE_DIR, "settings/schedules.json")
DB_PATH = os.path.join(BASE_DIR, "db", "music.sqlite3")

_DB_SESSION_FACTORY = None


def _get_db_session_factory():
    global _DB_SESSION_FACTORY

    if _DB_SESSION_FACTORY is not None:
        return _DB_SESSION_FACTORY

    if not os.path.exists(DB_PATH):
        return None

    engine = create_sqlite_engine(DB_PATH)
    _DB_SESSION_FACTORY = create_session_factory(engine)
    return _DB_SESSION_FACTORY


def _normalize_track_name(track_name: str) -> str:
    normalized = track_name.strip()
    if normalized.lower().endswith(".wav"):
        normalized = normalized[:-4]
    return normalized


def _extract_sound_file_name(
    minute_settings: MinuteSettings | dict[str, Any],
) -> Optional[str]:
    if isinstance(minute_settings, dict):
        value = minute_settings.get("sound_file_name")
    else:
        value = minute_settings.sound_file_name

    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _extract_sound_types(minute_settings: MinuteSettings | dict[str, Any]) -> list[str]:
    if isinstance(minute_settings, dict):
        raw_types = minute_settings.get("sound_types")
    else:
        raw_types = minute_settings.sound_types

    if raw_types is None:
        return []

    type_names: list[str] = []
    for item in raw_types:
        if isinstance(item, AudioType):
            type_names.append(item.value)
            continue

        text = str(item).strip()
        if not text:
            continue

        try:
            type_names.append(AudioType(text).value)
        except ValueError:
            continue

    return list(dict.fromkeys(type_names))


def _resolve_track_path_by_name(track_name: str) -> Optional[str]:
    session_factory = _get_db_session_factory()
    if session_factory is None:
        return None

    with session_factory() as session:
        track = get_track_by_name(session, _normalize_track_name(track_name))
        if track is not None and os.path.exists(track.file_path):
            return track.file_path

    return None


def _resolve_track_path_by_types(type_names: Sequence[str]) -> Optional[str]:
    session_factory = _get_db_session_factory()
    if session_factory is None:
        return None

    shuffled_types = list(type_names)
    random.shuffle(shuffled_types)

    with session_factory() as session:
        for type_name in shuffled_types:
            track = get_random_track_by_type(session, type_name)
            if track is not None and os.path.exists(track.file_path):
                return track.file_path

    return None


def play_sound(sound_file_path: str) -> None:
    fs, data = wavfile.read(sound_file_path)
    sd.play(data, fs)
    sd.wait()


def load_schedule(path: str) -> WeeklySchedule:
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
            schedules: WeeklySchedule = data

        except json.JSONDecodeError:
            return {}

        return schedules


def _find_hour_settings(daily_schedule: list[dict], hour: int) -> Optional[dict]:
    return next((s for s in daily_schedule if s.get("hour") == hour), None)


def _is_japanese_holiday(date: datetime.date) -> bool:
    if jpholiday is None:
        return False
    return jpholiday.is_holiday(date)


def get_minute_setting(
    schedule: WeeklySchedule, now: datetime.datetime
) -> Optional[MinuteSettings]:
    today_schedule = []

    is_holiday = _is_japanese_holiday(now.date())
    print(f"Is today a holiday? {is_holiday}")
    if is_holiday:
        today_schedule = schedule.get("holiday", [])

    if today_schedule == []:
        weekday_index = now.strftime("%A").lower()
        today_schedule = schedule.get(weekday_index, [])

    print(today_schedule)
    hour = now.hour
    minute = now.minute

    hour_settings = _find_hour_settings(today_schedule, hour)
    if hour_settings is None:
        return None

    minutes_list = hour_settings.get("minutes")
    if minutes_list and minute not in minutes_list:
        return None

    minute_settings = hour_settings.get("minute_settings") or {}
    result = minute_settings.get(str(minute))
    if result is None:
        return {}
    return result


def get_sound_file(minute_settings: Optional[MinuteSettings]) -> str:
    if minute_settings is None:
        raise ValueError("minute_settings が指定されていません")

    sound_file_name = _extract_sound_file_name(minute_settings)

    # 曲名指定がある場合は最優先。タイプ指定は無視する。
    if sound_file_name:
        resolved_by_name = _resolve_track_path_by_name(sound_file_name)
        if resolved_by_name:
            return resolved_by_name
        raise FileNotFoundError(
            f"指定された楽曲がDBに見つかりません: {_normalize_track_name(sound_file_name)}"
        )

    # タイプ未指定なら ALARM をデフォルト扱い
    sound_types = _extract_sound_types(minute_settings) or [AudioType.ALARM.value]

    resolved_by_type = _resolve_track_path_by_types(sound_types)
    if resolved_by_type:
        return resolved_by_type

    raise FileNotFoundError(
        f"指定タイプに一致する楽曲がDBに見つかりません: {', '.join(sound_types)}"
    )


def main() -> None:
    now = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
    schedule = load_schedule(SCHEDULE_PATH)
    minute_setting = get_minute_setting(schedule, now)

    if minute_setting is not None:
        sound_file_path = get_sound_file(minute_setting)
        play_sound(sound_file_path)


if __name__ == "__main__":
    main()
