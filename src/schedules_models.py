from typing import List, TypedDict


class HourlyScheduleItemType(TypedDict):
    hour: int


DailyScheduleType = List[HourlyScheduleItemType]
WeeklyScheduleType = List[DailyScheduleType]
