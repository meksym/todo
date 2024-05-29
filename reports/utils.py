from datetime import timedelta
from models import Duration


def minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def add_time(timeline: list[int], duration: Duration):
    hour = duration.start.hour

    if hour == duration.end.hour:
        timeline[hour] += minutes(duration.value)
        return

    following = duration.start \
        .replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    timeline[hour] = minutes(following - duration.start)

    # Next day
    if following.hour == 0:
        return

    hour += 1
    remainder = minutes(duration.end - following)

    while remainder >= 60:
        timeline[hour] += 60

        remainder -= 60
        hour += 1
        if hour > 23:
            return

    if hour < 24:
        timeline[hour] += remainder
