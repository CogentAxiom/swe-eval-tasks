"""Operating Day calendar (PGO Market Rules 9.4.1)."""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Tuple

HOURS = range(1, 25)          # Hour Ending labels on a 24-hour Operating Day
INTERVALS_PER_HOUR = 4        # 15-minute Settlement Intervals
INTERVAL_HOURS = Decimal("0.25")


def _nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7, weeks=n - 1)


def operating_hours(day: date) -> List[Tuple[int, str]]:
    """(hour_ending, dst_flag) for each hour of the Operating Day, in order.

    Spring-forward day (2nd Sunday of March): no HE3, 23 hours.
    Fall-back day (1st Sunday of November): HE2 twice (dst_flag N then Y), 25 hours.
    """
    if day == _nth_sunday(day.year, 3, 2):
        return [(he, "N") for he in HOURS if he != 3]
    if day == _nth_sunday(day.year, 11, 1):
        return [(1, "N"), (2, "N"), (2, "Y")] + [(he, "N") for he in range(3, 25)]
    return [(he, "N") for he in HOURS]
