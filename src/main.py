import datetime
import glob
import json
import os
import random
from typing import Optional
from zoneinfo import ZoneInfo

import jpholiday

from scipy.io import wavfile
import sounddevice as sd
from schedules_models import MinuteSettings, WeeklySchedule


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE_PATH = os.path.join(BASE_DIR, "settings/schedules.json")
SOUND_BASE_PATH = os.path.join(BASE_DIR, "sounds")
USER_SOUND_PATH = os.path.join(SOUND_BASE_PATH, "user")
DEFAULT_SOUND_PATH = os.path.join(SOUND_BASE_PATH, "default")


def _collect_sound_files() -> list[str]:
    # ユーザーが追加した楽曲（sounds/user/*.wav）を優先する
    user_files = glob.glob(os.path.join(USER_SOUND_PATH, "*.wav"))
    if user_files:
        return user_files

    # ユーザー楽曲がなければ、同梱のデフォルト楽曲（sounds/default/*.wav）を使う
    default_files = glob.glob(os.path.join(DEFAULT_SOUND_PATH, "*.wav"))
    if default_files:
        return default_files

    # 音源が1つもない場合は空リストを返す
    return []


def play_sound(sound_file_path: str) -> None:
    # 音声ファイルを読み込む
    fs, data = wavfile.read(sound_file_path)

    # 音声を再生する
    sd.play(data, fs)
    sd.wait()


def load_schedule(path: str) -> WeeklySchedule:
    # スケジュールを読み込む
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

    # 祝日は holiday を優先、なければ sunday を使う
    is_holiday = _is_japanese_holiday(now.date())
    print(f"Is today a holiday? {is_holiday}")
    if is_holiday:
        today_schedule = schedule.get("holiday", [])

    if today_schedule == []:
        weekday_index = now.strftime("%A").lower()
        today_schedule = schedule.get(weekday_index, [])

    print(today_schedule)
    # 現在の時刻を取得する
    hour = now.hour
    minute = now.minute

    # 現在の時刻に対応する設定を取得する
    hour_settings = _find_hour_settings(today_schedule, hour)
    if hour_settings is None:
        return None

    # 分の設定を取得する
    minutes_list = hour_settings.get("minutes")

    if minutes_list:
        if minute not in minutes_list:
            return None

    minute_settings = hour_settings.get("minute_settings") or {}
    return minute_settings.get(str(minute), {})


def get_sound_file(minute_settings: Optional[MinuteSettings]) -> str:
    # 楽曲の一覧を取得する
    files = _collect_sound_files()

    if minute_settings:
        target_file = minute_settings.get("sound_file_name")
        if target_file:
            for file in files:
                if target_file in file:
                    return file

    return random.choice(files)


def main() -> None:
    # 現在時刻を取得する
    now = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
    # スケジュールの読み込む
    schedule = load_schedule(SCHEDULE_PATH)
    # スケジュールに基づいて音を鳴らすか判定する
    minute_setting = get_minute_setting(schedule, now)

    if minute_setting is not None:
        # 楽曲ファイルを取得する
        sound_file_path = get_sound_file(minute_setting)
        # 曲を再生する
        play_sound(sound_file_path)


if __name__ == "__main__":
    main()
