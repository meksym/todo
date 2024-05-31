from typing import IO
from . import utils
from peewee import fn
# from matplotlib import pyplot
from datetime import timedelta
from models import database, Task, Duration, utc_now
from aiogram.utils.i18n import gettext as _


def today(task: Task, file: IO):
    # The pyplot module from matplotlib has been
    # imported to avoid errors when executing Celery tasks.

    # > billiard.exceptions.WorkerLostError:
    # >Worker exited prematurely: signal 6 (SIGABRT) Job: 1

    from matplotlib import pyplot

    now = utc_now().date()

    with database:
        durations = (
            Duration
            .select()
            .where(
                Duration.task == task,
                fn.DATE(Duration.start) >= now
            )
            .order_by(Duration.start)
            .limit(500)
        )
        if not len(durations):
            raise ValueError()

    timeline = [0] * 24

    for duration in durations:
        utils.add_time(timeline, duration)

    hours = list(range(24))

    pyplot.close('all')
    pyplot.figure(0, (5, 2.5), 300)
    pyplot.style.use('seaborn-v0_8-dark')

    pyplot.title(_('Activity time'))
    pyplot.xlabel(_('Hour'), fontsize='xx-small')
    pyplot.ylabel(_('Minute'), fontsize='xx-small')
    pyplot.xticks(hours, fontsize='xx-small')
    pyplot.yticks(range(0, 61, 10), fontsize='xx-small')
    pyplot.xlim(0, 23)
    pyplot.ylim(0, 60)
    pyplot.bar(hours, timeline)

    pyplot.savefig(file, format='png')
    pyplot.close('all')


def week(task: Task, file: IO):
    return days(task, 6, file)


def month(task: Task, file: IO):
    return days(task, 29, file)


def days(task: Task, count: int, file: IO):
    # The pyplot module from matplotlib has been
    # imported to avoid errors when executing Celery tasks.
    from matplotlib import pyplot

    date = fn.DATE(Duration.start)
    duration = fn.SUM(Duration.end - Duration.start).alias('duration')

    now = utc_now().date()
    startswith = now - timedelta(days=count)

    days = [now - timedelta(days=i) for i in range(count, -1, -1)]
    hours = [0.0] * (count + 1)

    with database:
        records = (
            Duration
            .select(date.alias('date'), duration)
            .where(
                Duration.task == task,
                date >= startswith
            )
            .group_by(date)
            .order_by(date)
            .limit(500)
        )
        if not len(records):
            raise ValueError()

    for record in records:
        hours[days.index(record.date)] += utils.minutes(record.duration) / 60

    days = [str(date.day) for date in days]

    pyplot.close('all')
    pyplot.figure(0, (5, 2.5), 300)
    pyplot.style.use('seaborn-v0_8-dark')

    pyplot.title(_('Activity time'))
    pyplot.xlabel(_('Day'), fontsize='xx-small')
    pyplot.ylabel(_('Hours'), fontsize='xx-small')
    pyplot.xticks(range(count+1), labels=days, fontsize='xx-small')
    pyplot.bar(range(count+1), hours)

    pyplot.savefig(file, format='png')
    pyplot.close('all')
