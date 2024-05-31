import link
import settings
from models import database, Account, Task

from peewee import DoesNotExist
from typing import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.utils.i18n import gettext as _
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.i18n.middleware import SimpleI18nMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, User
from aiogram.dispatcher.event.bases import UNHANDLED


Handler = Callable[[TelegramObject, dict], Awaitable]


class AccountMiddleware(BaseMiddleware):
    async def __call__(
        self, handler: Handler, event: TelegramObject, data: dict
    ):
        user = data.get('event_from_user')

        if isinstance(user, User):
            language_code = settings.LANGUAGE_CODE
            languages = (code for code, _ in settings.LANGUAGES)

            if user.language_code in languages:  # type: ignore
                language_code = user.language_code

            with database:
                account, _ = Account.get_or_create(
                    id=user.id,
                    defaults={'language_code': language_code}
                )
            data['account'] = account

        return await handler(event, data)


class LanguageMiddleware(SimpleI18nMiddleware):
    async def get_locale(self, event: TelegramObject, data: dict):
        account = data.get('account')

        if (
            isinstance(account, Account)
            and account.language_code in self.i18n.available_locales
        ):
            return account.language_code

        return await super().get_locale(event, data)


class TaskMiddleware(BaseMiddleware):
    '''
    Using the context parameter "params", it locates the
    Task object and enriches the request context with it. If the
    parameter or object is absent, it terminates request processing.
    '''

    async def __call__(
        self, handler: Handler, callback: CallbackQuery, data: dict
    ):
        account = data.get('account')
        params = data.get('params')

        task_id = None
        if isinstance(params, dict):
            task_id = params.get('id')

        if isinstance(account, Account) and isinstance(task_id, int):
            task = None
            with database:
                try:
                    # Does not depend on the account's active folder
                    task = Task.select().where(Task.id == task_id,
                                               Task.account == account).get()
                except DoesNotExist:
                    pass

            if task:
                data['task'] = task
                return await handler(callback, data)

        return await callback.answer(
            _("Sorry, but I couldn't find the specified task.")
        )


class CreateTaskOuterMiddleware(BaseMiddleware):
    async def __call__(
        self, handler: Handler, event: TelegramObject, data: dict
    ):
        response = await handler(event, data)

        if isinstance(event, Message) and event.text and response is UNHANDLED:
            builder = InlineKeyboardBuilder()

            builder.button(
                text=_('✅ YES'), callback_data=link.Call.Task._end_create
            )
            builder.button(
                text=_('❌ NO'), callback_data=link.Call.cancel
            )

            input = event.text.split('\n\n', 1)
            name, description = input if len(input) == 2 else (input[0], None)

            lines = [
                _('Do I need to create tasks?'),
                _('Name: %s') % name,
            ]
            if description:
                lines.append(_('Description: %s') % description)

            text = '\n\n'.join(lines)
            markup = builder.as_markup()

            await data['state'].set_data({
                'name': name, 'description': description
            })
            return await event.reply(text, reply_markup=markup)

        return response
