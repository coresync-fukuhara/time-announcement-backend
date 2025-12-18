import datetime
import glob
import json
import os
import random
from typing import List
from zoneinfo import ZoneInfo

from scipy.io import wavfile
import sounddevice as sd
from schedules_models import HourlyScheduleItemType


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE_PATH = os.path.join(BASE_DIR, "settings/schedules.json")
SOUND_PATH = os.path.join(BASE_DIR, "sounds")


def play_sound() -> None:
    # 楽曲の一覧を取得する
    files = glob.glob(f"{SOUND_PATH}/*.wav")

    # ランダムに楽曲を選択して再生する
    fs, data = wavfile.read(random.choice(files))

    # 音声を再生する
    sd.play(data, fs)
    sd.wait()


def load_schedule(path: str) -> List[List[HourlyScheduleItemType]]:
    # スケジュールを読み込む
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
            schedules: List[List[HourlyScheduleItemType]] = data

        except json.JSONDecodeError:
            return {}

        return schedules


def should_run(
    schedule: List[List[HourlyScheduleItemType]], now: datetime.datetime
) -> bool:
    # 曜日を取得する (0=月曜, 6=日曜)
    weekday = now.weekday() % 7
    # 今日のスケジュールを取得する
    today_schedule = schedule[weekday]
    # 現在の時刻を取得する
    hour = now.hour
    minute = now.minute

    print(f"現在時刻: {hour}時{minute}分")

    # 現在の時刻に対応する設定を取得する
    hour_settings = next((s for s in today_schedule if s["hour"] == hour), None)

    # 設定が存在しない場合は実行しない
    if hour_settings is None:
        return False

    # 分が0分でない場合は実行しない
    if minute != 0:
        return False

    return True


def main() -> None:
    # 現在時刻を取得する
    now = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
    # スケジュールの読み込む
    schedule = load_schedule(SCHEDULE_PATH)
    # スケジュールに基づいて音を鳴らすか判定する
    if should_run(schedule, now):
        # 曲を再生する
        play_sound()


if __name__ == "__main__":
    main()
