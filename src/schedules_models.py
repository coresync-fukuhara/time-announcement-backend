from typing import Dict, List, Optional, TypedDict


class MinuteSettingType(TypedDict):
    sound_file_name: str


class HourlyScheduleItemType(TypedDict):
    hour: int
    minutes: Optional[List[int]]
    minute_settings: Optional[Dict[str, MinuteSettingType]]


DailyScheduleType = List[HourlyScheduleItemType]


class WeeklyScheduleType(TypedDict):
    monday: DailyScheduleType
    tuesday: DailyScheduleType
    wednesday: DailyScheduleType
    thursday: DailyScheduleType
    friday: DailyScheduleType
    saturday: DailyScheduleType
    sunday: DailyScheduleType
