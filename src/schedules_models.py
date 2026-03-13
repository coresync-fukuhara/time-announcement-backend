from typing import Dict, List, Optional, TypedDict


class MinuteSettingType(TypedDict):
    sound_file_name: str


class HourlyScheduleItemType(TypedDict):
    hour: int
    minutes: Optional[List[int]]
    minute_settings: Optional[Dict[str, MinuteSettingType]]


DailyScheduleType = List[HourlyScheduleItemType]
WeeklyScheduleType = List[DailyScheduleType]
