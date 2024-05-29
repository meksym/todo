import pytz

import link
from settings import LANGUAGES
from models import Account, Task
from state import ChangeTimezone

from aiogram import Router, Bot, F, types
from aiogram.filters import Command
from aiogram.utils import keyboard
from aiogram.utils import formatting
from aiogram.utils.i18n import gettext as _
from aiogram.fsm.context import FSMContext


router = Router()
timezones_url = (
    'https://en.wikipedia.org/wiki/List_of_tz_database_time_zones'
    '#:~:text=numeric%20UTC%20offsets.-,List,-%5Bedit%5D'
)


@router.message(
    Command(link.Cmd.start)
)
async def start(
    message: types.Message
):
    btn_create = types.KeyboardButton(text=str(link.Text.create))
    btn_help = types.KeyboardButton(text=str(link.Text.help))
    btn_list = types.KeyboardButton(text=str(link.Text.list))
    btn_settings = types.KeyboardButton(text=str(link.Text.settings))
    btn_folders = types.KeyboardButton(text=str(link.Text.folders))

    markup = types.ReplyKeyboardMarkup(
        keyboard=[
            [btn_create], [btn_list, btn_folders], [btn_help, btn_settings]
        ]
    )

    await message.answer(_('Hello!'), reply_markup=markup)
    await help(message)


@router.message(
    F.text == link.Text.help
)
@router.message(
    Command(link.Cmd.help)
)
async def help(message: types.Message):
    text = _(
        'This is a personal management tool that will help you better '
        'manage your time, set goals, and track progress.\n\n'
        'You can work with tasks and, if necessary, use the task '
        'grouping feature to better organize your activities. '
        'You can also create reminders for tasks at specified times.\n\n'
        'Additionally, there is an extra feature for tracking your '
        'productivity – timers and reports. You can use timers to '
        'record the time spent on tasks, and based on this data, you '
        'can generate a report – an image with a histogram.\n\n'
        'This tool will help you plan your day more effectively, stay '
        'organized, and achieve your goals.'
    )
    await message.answer(text)


@router.callback_query(
    F.data == link.Callback.cancel
)
async def cancel(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot
):
    await state.clear()
    await callback.answer(_('Сancelled'))

    if callback.message:
        await bot.delete_message(
            callback.message.chat.id,
            callback.message.message_id
        )


def get_settings(account: Account) -> tuple[str, types.InlineKeyboardMarkup]:
    text = _(
        'Your settings\n\n'
        'Current language: %s\n'
        'Time zone: %s'
    )
    text %= (account.language, account.timezone)

    builder = keyboard.InlineKeyboardBuilder()
    builder.button(
        text=_('🌐 Change language'),
        callback_data=link.Callback.change_language
    )
    builder.button(
        text=_('🌍 Change time zone'),
        callback_data=link.Callback.change_timezone
    )

    if account.folders.count() > 0:  # type: ignore
        builder.button(
            text=_('📁 Folders'),
            callback_data=link.Callback.folder_list
        )
        folder = account.active_folder
        name = folder.name if folder else _('Main folder')

        text += _('\nActive folder: %s') % name
    else:
        builder.button(
            text=_('📁 Create folder'),
            callback_data=link.Callback.folder_create
        )
    builder.adjust(1)

    folders = account.folders.count()  # type: ignore
    tasks = account.tasks.count()  # type: ignore
    completed = account.tasks \
        .where(Task.is_done == True).count()  # noqa # type: ignore
    end = ''

    if tasks:
        end += _('You have %s tasks, %s of which are completed!\n') % \
            (tasks, completed)
    if folders:
        end += _('You have %s folders!\n') % folders
    if end:
        text += '\n\n' + end

    return text, builder.as_markup()


@router.message(
    Command(link.Cmd.settings)
)
@router.message(
    F.text == link.Text.settings
)
async def settings(message: types.Message, account: Account):
    text, markup = get_settings(account)

    await message.answer(text, reply_markup=markup)


@router.callback_query(
    F.data == link.Callback.back_to_settings
)
async def back_to_settings(
    callback: types.CallbackQuery, bot: Bot, account: Account
):
    text, markup = get_settings(account)

    if not callback.message:
        return await bot.send_message(
            account.id, text, reply_markup=markup  # type: ignore
        )

    chat, message = callback.message.chat.id, callback.message.message_id

    await bot.edit_message_text(text, chat, message)
    await bot.edit_message_reply_markup(chat, message, reply_markup=markup)


@router.callback_query(
    F.data == link.Callback.change_language
)
async def change_language(
    callback: types.CallbackQuery, bot: Bot, event_from_user: types.User
):
    builder = keyboard.InlineKeyboardBuilder()

    for code, name in LANGUAGES:
        builder.button(
            text=str(name),
            callback_data=f'{link.Callback.set_language}/{code}'
        )

    builder.button(
        text=_('⚙️ Back to settings'),
        callback_data=link.Callback.back_to_settings
    )
    builder.adjust(1)

    text = _('Choose a language')
    markup = builder.as_markup()

    if callback.message:
        chat, message = callback.message.chat.id, callback.message.message_id

        await bot.edit_message_text(text, chat, message)
        await bot.edit_message_reply_markup(chat, message, reply_markup=markup)
    else:
        await bot.send_message(event_from_user.id, text, reply_markup=markup)

    await callback.answer(text)


@router.callback_query(
    F.data.startswith(link.Callback.set_language)
)
async def set_language(callback: types.CallbackQuery, account: Account):
    language_code = callback.data.split('/')[-1]  # type: ignore

    if language_code in [available for available, __ in LANGUAGES]:
        account.language_code = language_code  # type: ignore
        account.save()

        await callback.answer(_('Language successfully changed.'))
    else:
        await callback.answer(_("I can't set this language."))


@router.callback_query(
    F.data == link.Callback.change_timezone
)
async def change_timezone(callback: types.CallbackQuery,
                          bot: Bot,
                          state: FSMContext,
                          event_from_user: types.User):
    text = _(
        'To update the time zone, you need to send it to me in the '
        'correct format. Below is the link to the list (TZ identifier) '
        'of possible options.'
    )
    link = formatting.TextLink(_('Link'), url=timezones_url)

    builder = keyboard.InlineKeyboardBuilder()
    builder.button(text=_('⬅️ Cancel'), callback_data='cancel')

    await callback.answer(_('Send me your preferred time zone'))
    message = await bot.send_message(
        event_from_user.id,
        **formatting.Text(text, '\n\n', link).as_kwargs(),
        reply_markup=builder.as_markup()
    )

    await state.set_state(ChangeTimezone.typing)
    await state.set_data(
        {'chat_id': message.chat.id, 'message_id': message.message_id}
    )


@router.message(
    ChangeTimezone.typing
)
async def set_timezone(message: types.Message,
                       bot: Bot,
                       state: FSMContext,
                       account: Account):
    timezone = message.text

    if timezone not in pytz.all_timezones_set:
        return await message.reply(
            _('Sorry, but this time zone is not valid. Please try again.')
        )

    account.timezone = timezone  # type: ignore
    account.save()

    data = await state.get_data()
    if 'chat_id' in data and 'message_id' in data:
        await bot.edit_message_reply_markup(**data)

    await message.reply(_('Time zone successfully changed.'))
    await state.clear()
