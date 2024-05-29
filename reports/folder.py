from . import utils
from peewee import fn
from typing import IO
from datetime import timedelta
from aiogram.utils.i18n import gettext as _
from models import Account, Folder, Task, Duration, utc_now


def today(account: Account, folder: Folder | None, file: IO):
    # The pyplot module from matplotlib has been
    # imported to avoid errors when executing Celery tasks.
    from matplotlib import pyplot

    records = (
        Task
        .select(Task, Duration)
        .join(Duration)
        .where(
            Task.account == account,
            Task.folder == folder,
            Task.is_done == False,  # noqa
            fn.DATE(Duration.start) == utc_now().date()
        )
        .order_by(Duration.start)
        .limit(500)
    )

    if not len(records):
        raise ValueError()

    timelines = {}

    for task in records:
        if task not in timelines:
            timelines[task] = [0] * 24

        utils.add_time(timelines[task], task.duration)

    hours = list(range(24))
    last_timeline = [0] * 24

    pyplot.close('all')
    pyplot.figure(0, (5, 3), 300)
    pyplot.style.use('seaborn-v0_8-dark')

    for task, timeline in timelines.items():
        pyplot.bar(hours, timeline, bottom=last_timeline, label=task.name)
        last_timeline = timeline

    pyplot.title(_('Activity time'))
    pyplot.xlabel(_('Hour'), fontsize='xx-small')
    pyplot.ylabel(_('Minute'), fontsize='xx-small')
    pyplot.xticks(hours, fontsize='xx-small')
    pyplot.yticks(range(0, 61, 10), fontsize='xx-small')
    pyplot.xlim(0, 23)
    pyplot.ylim(0, 65 + len(timelines)*5)
    pyplot.legend(
        loc='upper left',
        fancybox=True,
        shadow=True,
        fontsize='xx-small'
    )

    pyplot.savefig(file, format='png')
    pyplot.close('all')


def week(account: Account, folder: Folder | None, file: IO):
    return days(account, folder, 6, file)


def month(account: Account, folder: Folder | None, file: IO):
    return days(account, folder, 29, file)


def days(account: Account, folder: Folder | None, count: int, file: IO):
    # The pyplot module from matplotlib has been
    # imported to avoid errors when executing Celery tasks.
    from matplotlib import pyplot

    now = utc_now().date()
    startswith = now - timedelta(days=count)
    days = [now - timedelta(days=i) for i in range(count, -1, -1)]
    chronology = {}

    date = fn.DATE(Duration.start)
    duration = fn.SUM(Duration.end - Duration.start).alias('duration')

    records = (
        Task
        .select(Task, date, duration)
        .join(Duration)
        .where(
            Task.account == account,
            Task.folder == folder,
            date >= startswith
        )
        .group_by(Task, date)
        .order_by(date)
    )

    if not len(records):
        raise ValueError()

    for task in records:
        if task not in chronology:
            chronology[task] = [0] * (count + 1)

        chronology[task][days.index(task.date)] += \
            utils.minutes(task.duration) / 60

    length = len(chronology)
    days = [str(date.day) for date in days]
    last_hours = [0] * (count+1)

    pyplot.close('all')
    pyplot.figure(0, (4 + length//4, 2 + length//3), 300)
    pyplot.style.use('seaborn-v0_8-dark')

    for task, hours in chronology.items():
        pyplot.bar(range(count + 1), hours, bottom=last_hours, label=task.name)
        last_hours = hours

    pyplot.title(_('Activity time'))
    pyplot.xlabel(_('Day'), fontsize='xx-small')
    pyplot.ylabel(_('Hours'), fontsize='xx-small')
    pyplot.xticks(range(count + 1), labels=days, fontsize='xx-small')
    pyplot.yticks(range(15), fontsize='xx-small')
    pyplot.ylim(0, 15 + length//2)
    pyplot.legend(
        loc='upper left',
        fancybox=True,
        shadow=True,
        fontsize='xx-small'
    )

    pyplot.savefig(file, format='png')
    pyplot.close('all')
