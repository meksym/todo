import asyncio
import settings
from aiogram import Bot
from celery import Celery
from peewee import DoesNotExist
from models import Account, Task
from aiogram.utils.i18n import I18n
from handlers.utils import base_retrieve
from aiogram.utils.i18n import gettext as _


app = Celery('reminder', broker=settings.BROKER)


async def send(account_id: int, task_id: int):
    '''
    Coroutine for sending reminder messages.
    It will be executed asynchronously in a task queue.
    '''
    try:
        account = Account.get(id=account_id)
        task = Task.get(id=task_id)
    except DoesNotExist:
        return

    i18n = I18n(path=settings.LOCALES_PATH,
                default_locale=settings.LANGUAGE_CODE)
    bot = Bot(settings.TOKEN)

    with i18n.context(), i18n.use_locale(account.language_code):
        text, markup = base_retrieve(task)

        await bot.send_message(account.id, _('Reminder'))
        await bot.send_message(account.id, text, reply_markup=markup)

    await bot.session.close()


@app.task
def run(account_id: int, task_id: int):
    coroutine = send(account_id, task_id)
    asyncio.run(coroutine)
