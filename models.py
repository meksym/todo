# pyright: reportAssignmentType=false

import pytz
import peewee
import settings
from datetime import datetime, timedelta
from aiogram.utils.i18n import gettext as _


database = peewee.PostgresqlDatabase(
    settings.DB_NAME,
    user=settings.DB_USER,
    password=settings.DB_PASSWORD,
    host=settings.DB_HOST
)


def utc_now():
    return datetime.now(pytz.utc)


def init():
    with database:
        database.create_tables(
            [Account, Folder, Task, Duration]
        )
        database.execute_sql(
            'ALTER TABLE account '
            'ADD CONSTRAINT account_active_folder_fk '
            'FOREIGN KEY (active_folder_id, id) '
            'REFERENCES folder (id, account_id) '
            'ON DELETE SET NULL'
        )


class Account(peewee.Model):
    _timezones = [(tz, tz) for tz in pytz.all_timezones]

    # Id is identical to the corresponding field of a Telegram user
    id = peewee.BigIntegerField(primary_key=True)
    active_folder = peewee.DeferredForeignKey('Folder', null=True)
    timezone = peewee.CharField(choices=_timezones, default='Europe/Kiev')
    language_code = peewee.CharField(
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE
    )

    id: int
    active_folder: 'Folder | None'
    timezone: str
    language_code: str

    tasks: peewee.ModelSelect
    folders: peewee.ModelSelect

    @property
    def language(self):
        return dict(settings.LANGUAGES).get(
            self.language_code, settings.LANGUAGE_CODE  # type: ignore
        )

    class Meta:
        database = database


class Folder(peewee.Model):
    account = peewee.ForeignKeyField(
        Account,
        on_delete='CASCADE',
        backref='folders'
    )
    name = peewee.CharField(max_length=500)
    description = peewee.TextField(null=True)

    tasks: peewee.ModelSelect

    def __str__(self):
        return self.name

    class Meta:
        database = database
        constraints = [
            peewee.SQL('UNIQUE (id, account_id)'),
            peewee.SQL('UNIQUE (name, account_id)'),
        ]


class Task(peewee.Model):
    # To initialize the storage, the field
    # type must be changed to DeferredForeignKey
    folder = peewee.ForeignKeyField(
        Folder,
        null=True,
        backref='tasks'
    )
    account = peewee.ForeignKeyField(
        Account,
        on_delete='CASCADE',
        backref='tasks'
    )

    name = peewee.CharField(max_length=500)
    description = peewee.TextField(null=True)
    is_done = peewee.BooleanField(default=False)
    created_at = peewee.DateTimeField(default=utc_now)

    id: int
    folder: Folder | None
    account: Account
    name: str
    description: str
    is_done: bool
    created_at: datetime
    durations: peewee.ModelSelect

    # TODO: Different tasks should not have the same execution time!

    @property
    def localized_created_at(self) -> datetime:
        try:
            timezone = pytz.timezone(self.account.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            timezone = pytz.timezone('UTC')

        return self.created_at.astimezone(timezone)  # type: ignore

    def __str__(self):
        if self.name:
            return self.name
        return super().__str__()

    class Meta:
        database = database
        constraints = [
            peewee.SQL('UNIQUE (id, account_id)'),
            peewee.SQL(
                'FOREIGN KEY (folder_id, account_id) '
                'REFERENCES folder (id, account_id)'
                'ON DELETE CASCADE'
            )
        ]


class Duration(peewee.Model):
    task = peewee.ForeignKeyField(
        Task,
        on_delete='CASCADE',
        related_name='durations'
    )

    end = peewee.DateTimeField()
    start = peewee.DateTimeField()
    notes = peewee.TextField(null=True)

    task: Task
    end: datetime
    start: datetime
    notes: str | None

    # The date format to be used when converting between
    # string and datetime types for further transmission
    transition_date_format = '%Y-%m-%d %H:%M:%S.%f%z'

    def __str__(self) -> str:
        return str(self.end - self.start)

    @classmethod
    def convert_dates(cls, raw: dict):
        '''
        Takes a dict and converts the types of the start and end keys
        from string to datetime. If this is not possible, a ValueError
        will be raised.
        '''
        for attr in ('start', 'end'):
            if attr not in raw:
                raise ValueError(
                    f'The key {attr} is not represented in the provided dict'
                )

            date = raw[attr]
            if not isinstance(date, datetime):
                raw[attr] = datetime.strptime(date, cls.transition_date_format)

    @staticmethod
    def validate(
        task: Task, start: datetime, end: datetime, notes: str | None = None
    ):
        if start > end:
            raise ValueError(_('Can\'t process it. Invalid data received.'))

        query = task.durations.where(
            ((start <= Duration.start) & (Duration.start <= end))
            | ((start <= Duration.end) & (Duration.end <= end))
            | ((Duration.start <= start) & (start <= Duration.end))
            | ((Duration.start <= end) & (end <= Duration.end))
        )
        overlap = query.first()  # type: ignore

        if overlap is not None:
            # TODO: Update message text
            overlap_error_message = _(
                "Sorry, I can't register this entry for the task \"%s\" "
                "because there's already another one intersecting with "
                "it – its start %s (duration %s)"
            ) % (
                task.name,
                overlap.start.strftime('%d.%m.%Y, %H:%M'),
                (overlap.end - overlap.start)
            )
            if overlap.notes:
                overlap_error_message += " and note %s" % overlap.notes

            raise ValueError(overlap_error_message)

    @classmethod
    def create(cls, validate: bool = True, **attributes):
        if validate:
            cls.convert_dates(attributes)
            cls.validate(**attributes)
        return super().create(**attributes)

    @property
    def value(self) -> timedelta:
        return self.end - self.start

    class Meta:
        database = database
        constraints = [peewee.Check('"start" < "end"')]
