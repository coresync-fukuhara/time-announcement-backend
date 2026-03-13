import datetime
import glob
import json
import os
import random
from typing import Optional
from zoneinfo import ZoneInfo

from scipy.io import wavfile
import sounddevice as sd
from schedules_models import MinuteSettingType, WeeklyScheduleType


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


def load_schedule(path: str) -> WeeklyScheduleType:
    # スケジュールを読み込む
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
            schedules: WeeklyScheduleType = data

        except json.JSONDecodeError:
            return {}

        return schedules


def get_minute_setting(
    schedule: WeeklyScheduleType, now: datetime.datetime
) -> Optional[MinuteSettingType]:
    # 曜日のキー名を取得する（monday, tuesday, ...）
    weekday_index = now.strftime("%A").lower()

    # 今日のスケジュールを取得する
    today_schedule = schedule.get(weekday_index, [])
    # 現在の時刻を取得する
    hour = now.hour
    minute = now.minute

    # 現在の時刻に対応する設定を取得する
    hour_settings = next((s for s in today_schedule if s["hour"] == hour), None)

    # 設定が存在しない場合は実行しない
    if hour_settings is None:
        return None

    # 分の設定を取得する（省略時は 0 分のみとみなす）
    minutes_list = hour_settings.get("minutes")

    if minutes_list:
        # 分の設定に現在の分が含まれていない場合は実行しない
        if minute not in minutes_list:
            return None
    else:
        # minutes が指定されていない場合は 0 分のみ有効
        if minute != 0:
            return None

    minute_settings = hour_settings.get("minute_settings") or {}

    return minute_settings.get(str(minute), {})


def get_sound_file(minute_settings: Optional[MinuteSettingType]) -> str:
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
