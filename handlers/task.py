import pytz
import reports
import reminder
import tempfile
from math import ceil
from typing import Callable
from datetime import datetime
from peewee import DoesNotExist

import link
from middleware import TaskMiddleware
from filters import LinkFilter, without_state
from models import database, Account, Folder, Task, Duration, utc_now
from state import CreateDuration, CreateTask, UpdateTask, CreateReminder

from aiogram import Router, Bot, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils import keyboard
from aiogram.utils.i18n import gettext as _
from aiogram.utils.formatting import as_numbered_section


detail_router = Router()
detail_router.callback_query.middleware(TaskMiddleware())

router = Router()
router.include_router(detail_router)


def is_message(data):
    if (
        isinstance(data, dict)
        and 'message_id' in data
        and 'chat_id' in data
    ):
        return True


def parse(text: str) -> tuple[str, str | None]:
    data = text.split('\n\n', 1)
    name, description = data if len(data) == 2 else (data[0], None)
    return name, description


async def edit_callback_message(
    callback: types.CallbackQuery,
    bot: Bot,
    user_id: int,
    text: str,
    markup: types.InlineKeyboardMarkup | None
):
    if callback.message:
        msg: dict = {
            'chat_id': callback.message.chat.id,
            'message_id': callback.message.message_id
        }
        await bot.edit_message_text(text, **msg, reply_markup=markup)
    else:
        await bot.send_message(user_id, text, reply_markup=markup)


def create_list(account: Account,
                page: int) -> tuple[str, types.InlineKeyboardMarkup]:
    # "id=None" is main folder
    folder = Folder(id=None, name=_('Main folder'), account=account)
    if account.active_folder:
        folder = account.active_folder

    with database:
        query = (
            folder.tasks  # type: ignore
            .where(Task.is_done == False)  # noqa
            .order_by(Task.created_at.desc())  # type: ignore
        )

        count = query.count()
        per_page = 15
        pages = ceil(count / per_page)

        builder = keyboard.InlineKeyboardBuilder()

        if page > pages:
            text = _(
                'There is no incomplete task in the folder "%s". '
                'Create a new one if necessary.'
            )
            text %= folder.name

            builder.button(
                text=_('🆕 Create task'),
                callback_data=link.Call.Task.create
            )

            return text, builder.as_markup()

        tasks = query.paginate(page, per_page)
        tasks = list(tasks)

    for number, task in enumerate(tasks, 1):
        data = link.build(link.Call.Task.retrieve, id=task.id)
        builder.button(text=str(number), callback_data=data)

    pagination = 0

    if page > 1:
        data = link.build(link.Call.Task.list, page=page-1)
        builder.button(text=_('⬅️ Previous page'), callback_data=data)
        pagination += 1
    if page < pages:
        data = link.build(link.Call.Task.list, page=page+1)
        builder.button(text=_('➡️ Next page'), callback_data=data)
        pagination += 1

    builder.button(
        text=_('🆕 Create task'), callback_data=link.Call.Task.create
    )
    builder.button(
        text=_('🕰️📈 Reports'), callback_data=link.Call.Task.folder_reports
    )

    length = len(tasks)
    rows = length // 5
    remainder = length % 5
    sheet = rows * [5]

    if rows and remainder == 1:
        sheet[-1] += remainder
    elif remainder:
        sheet.append(remainder)
    if pagination:
        sheet.append(pagination)
    sheet.extend([1, 1])

    builder.adjust(*sheet)

    title = _(
        'Below is the list of your unfinished tasks in the folder "%s". '
        'To make changes to a task, click on the corresponding number.\n'
    )
    title %= folder.name
    text, entities = as_numbered_section(title, *tasks).render()

    return text, builder.as_markup()


@router.message(
    Command(link.Cmd.list)
)
@router.message(
    F.text == link.Text.list
)
async def listing_on_message(message: types.Message, account: Account):
    text, markup = create_list(account, 1)
    await message.answer(text, reply_markup=markup)


@router.callback_query(
    LinkFilter(link.Call.Task.list)
)
async def listing_on_callback(
    callback: types.CallbackQuery, bot: Bot, account: Account, params: dict
):
    page = params.get('page', 1)

    if not isinstance(page, int) or page < 1:
        return await callback.answer(
            _("Sorry, but I can't process it because the page is wrong. ):")
        )

    text, markup = create_list(account, page)
    await edit_callback_message(
        callback, bot, account.id, text, markup  # type: ignore
    )


@router.message(F.text == link.Text.create)
@router.callback_query(F.data == link.Call.Task.create)
@router.message(
    Command(link.Cmd.create)
)
async def start_create(event: types.Message | types.CallbackQuery,
                       bot: Bot,
                       account: Account,
                       state: FSMContext):
    text = _(
        'To create a new task, send me its name and, '
        'if necessary, its description via a line.'
    )

    builder = keyboard.InlineKeyboardBuilder()
    builder.button(text=_('⬅️ Cancel'), callback_data=link.Call.cancel)
    markup = builder.as_markup()

    if isinstance(event, types.Message):
        explanation = await event.reply(text, reply_markup=markup)
    else:
        await event.answer(text)
        explanation = await bot.send_message(account.id,  # type: ignore
                                             text, reply_markup=markup)
    data = {}
    data['explanation'] = {
        'chat_id': explanation.chat.id,
        'message_id': explanation.message_id
    }

    await state.set_data(data)
    await state.set_state(CreateTask.typing)


@router.message(CreateTask.typing)
async def end_create(message: types.Message,
                     bot: Bot,
                     account: Account,
                     state: FSMContext):

    if not message.text:
        await message.reply(_("Sorry, but I can't process it. Try again."))
        return await start_create(message, bot, account, state)

    with database:
        name, description = parse(message.text)
        folder = Folder(id=None, name=_('Main folder'), account=account)

        if account.active_folder:
            folder = account.active_folder

        task = Task.create(
            account=account,
            folder=folder,
            name=name,
            description=description,
        )

    text, markup = base_retrieve(task)

    await message.answer(_('Task "%s" successfully created.') % name)
    await message.answer(text, reply_markup=markup)

    data = await state.get_data()
    explanation = data.get('explanation')

    if is_message(explanation):
        await bot.edit_message_reply_markup(**explanation)  # type: ignore

    await state.clear()


@router.callback_query(
    F.data == link.Call.Task._end_create
)
async def _end_create(
    callback: types.CallbackQuery,
    bot: Bot,
    state: FSMContext,
    account: Account
):
    data = await state.get_data()

    try:
        name = data['name']
        description = data['description']
    except KeyError:
        return

    with database:
        folder = Folder(id=None, name=_('Main folder'), account=account)
        if account.active_folder:
            folder = account.active_folder

        task = Task.create(
            account=account,
            folder=folder,
            name=name,
            description=description,
        )

    text, markup = base_retrieve(task)

    message = callback.message
    if message:
        await bot.send_message(message.chat.id, text, reply_markup=markup)
        await bot.edit_message_reply_markup(
            message.chat.id, message.message_id
        )
    await callback.answer(_('Task "%s" successfully created.') % name)


def base_retrieve(task: Task) -> tuple[str, types.InlineKeyboardMarkup]:

    created_at = task.localized_created_at.strftime('%d.%m.%Y, %H:%M')
    folder = Folder(name=_('Main folder'))

    if task.folder:
        folder = task.folder

    fields = [
        _('Your task from the folder "%s"') % folder.name,
        _('Name: %s') % task.name,
        _('Created by: %s') % created_at,
    ]
    if task.description:
        fields.insert(2, _('Description: %s') % task.description)

    id = task.id
    builder = keyboard.InlineKeyboardBuilder()

    builder.button(
        text=_('✅ Mark done'),
        callback_data=link.build(link.Call.Task.mark_done, id=id)
    )
    builder.button(
        text=_('🔄 Update'),
        callback_data=link.build(link.Call.Task.update, id=id)
    )
    builder.button(
        text=_('📁 Active folder'),
        callback_data=link.Call.Task.list
    )
    builder.button(
        text=_('❌ Remove'),
        callback_data=link.build(link.Call.Task.remove, id=id)
    )
    builder.button(
        text=_('⏲️ Countdown'),
        callback_data=link.build(link.Call.Task.start_countdown, id=id)
    )
    builder.button(
        text=_('🔔 Reminder'),
        callback_data=link.build(link.Call.Task.start_reminder, id=id)
    )
    if task.durations.count():  # type: ignore
        builder.button(
            text=_('🕰️📈 Reports'),
            callback_data=link.build(link.Call.Task.task_reports, id=id)
        )
    builder.adjust(2, 2, 2, 1)

    text = '\n\n'.join(fields)
    markup = builder.as_markup()

    return text, markup


@detail_router.callback_query(
    LinkFilter(link.Call.Task.retrieve)
)
async def retrieve(
    callback: types.CallbackQuery,
    task: Task,
    bot: Bot,
    event_from_user: types.User,
):
    text, markup = base_retrieve(task)
    await edit_callback_message(
        callback, bot, event_from_user.id, text, markup
    )


@detail_router.callback_query(
    LinkFilter(link.Call.Task.mark_done)
)
async def mark_done(
    callback: types.CallbackQuery, task: Task, bot: Bot,
):
    task.is_done = True  # type: ignore
    task.save()

    text = _('The task "%s" has been successfully marked as completed.')
    await callback.answer(text % task.name)

    if callback.message:
        builder = keyboard.InlineKeyboardBuilder()
        builder.button(
            text=_('📁 Active folder'),
            callback_data=link.Call.Task.list
        )

        await bot.edit_message_reply_markup(
            callback.message.chat.id,
            callback.message.message_id,
            reply_markup=builder.as_markup()
        )


@detail_router.callback_query(
    LinkFilter(link.Call.Task.update)
)
async def start_update(
    callback: types.CallbackQuery,
    task: Task,
    bot: Bot,
    state: FSMContext,
    event_from_user: types.User
):
    text = _(
        'To update the details of the task "%s" send me '
        'a new name and if necessary a new description.'
    )
    text %= task.name

    builder = keyboard.InlineKeyboardBuilder()
    builder.button(text=_('Cencel'), callback_data=link.Call.cancel)

    await callback.answer(text)
    message = await bot.send_message(
        event_from_user.id, text, reply_markup=builder.as_markup()
    )

    data = {
        'task_id': task.id,
        'explanation': {
            'chat_id': message.chat.id,
            'message_id': message.message_id,
        }
    }
    if callback.message:
        data['source'] = {
            'chat_id': callback.message.chat.id,
            'message_id': callback.message.message_id,
        }

    await state.set_state(UpdateTask.typing)
    await state.set_data(data)


@router.message(UpdateTask.typing)
async def end_update(
    message: types.Message,
    bot: Bot,
    state: FSMContext,
    account: Account
):
    if not message.text:
        return await message.reply(
            _("Sorry, but I can't process it. Try again.")
        )

    data = await state.get_data()
    id = data.pop('task_id', None)
    does_not_exist = _('Update task does not exist ):')

    if not isinstance(id, int):
        return message.reply(does_not_exist)

    with database:
        try:
            task = Task \
                .select().where(Task.id == id, Task.account == account).get()
        except DoesNotExist:
            return message.reply(does_not_exist)

        name, description = parse(message.text)

        task.name = name
        if description:
            task.description = description
        task.save()

    explanation = data.get('explanation')
    if is_message(explanation):
        await bot.edit_message_reply_markup(**explanation)  # type: ignore

    source = data.get('source')
    if is_message(source):
        text, markup = base_retrieve(task)
        await bot.edit_message_text(text, reply_markup=markup,
                                    **source)  # type: ignore

    await state.clear()
    await message.answer(_('Task "%s" successfully updated.') % name)


@detail_router.callback_query(
    LinkFilter(link.Call.Task.remove)
)
async def start_remove(
    callback: types.CallbackQuery,
    task: Task,
    bot: Bot,
    event_from_user: types.User
):
    text = _('Are you sure you want to delete task "%s"?') % task.name

    builder = keyboard.InlineKeyboardBuilder()
    builder.button(
        text=_('❌ Confirm deletion'),
        callback_data=link.build(link.Call.Task.confirm_remove, id=task.id)
    )
    builder.button(text=_('⬅️ Cancel'), callback_data=link.Call.cancel)

    markup = builder.as_markup()
    chat_id = event_from_user.id

    await callback.answer(text)
    await edit_callback_message(callback, bot, chat_id, text, markup)


@detail_router.callback_query(
    LinkFilter(link.Call.Task.confirm_remove)
)
async def end_remove(
    callback: types.CallbackQuery,
    task: Task,
    bot: Bot,
    event_from_user: types.User
):
    chat_id = event_from_user.id
    text = _('Task "%s" successfully deleted!') % task.name

    task.delete_instance()

    await callback.answer(text)
    await edit_callback_message(callback, bot, chat_id, text, None)


@detail_router.callback_query(
    LinkFilter(link.Call.Task.start_countdown)
)
async def start_countdown(
    callback: types.CallbackQuery,
    bot: Bot,
    event_from_user: types.User,
    task: Task
):
    started_at = utc_now()
    builder = keyboard.InlineKeyboardBuilder()
    complete_link = link.build(
        link.Call.Task.complete_countdown,
        id=task.id,
        start=started_at.strftime(Duration.transition_date_format),
    )

    builder.button(
        text=_('⏰ Complete the countdown'),
        callback_data=complete_link
    )
    builder.button(
        text=_('❌ Cancel'),
        callback_data=link.Call.cancel
    )

    text = _(
        'The countdown for the task "%s" has started (%s). '
        'To complete it, please press the corresponding '
        '"⏰ Complete the countdown" button.'
    )
    text %= task.name, started_at.strftime('%d.%m.%Y, %H:%M')

    await callback.answer('OK')
    await bot.send_message(
        event_from_user.id,
        text,
        reply_markup=builder.as_markup()
    )


@detail_router.callback_query(
    LinkFilter(link.Call.Task.complete_countdown)
)
async def complete_countdown(
    callback: types.CallbackQuery,
    bot: Bot,
    state: FSMContext,
    event_from_user: types.User,
    task: Task,
    params: dict,
):
    message: dict | None = None
    end = utc_now()

    try:
        start = datetime.strptime(
            params['start'], Duration.transition_date_format
        )
    except Exception:
        start = None

    if callback.message:
        message = {
            'chat_id': callback.message.chat.id,
            'message_id': callback.message.message_id,
        }
        await bot.edit_message_reply_markup(**message)

    if not isinstance(start, datetime) or start > end:
        return await callback.answer(_('Button with incorrect data :('))

    builder = keyboard.InlineKeyboardBuilder()
    builder.button(text=_('✅YES'), callback_data=link.Call.Task.save_duration)
    builder.button(text=_('❌ REMOVE'), callback_data=link.Call.cancel)

    markup = builder.as_markup()
    text = _(
        'Would you like to record the execution time '
        '(start: %s, duration: %s) for the task "%s"?\n\n'
        'If yes, please click the corresponding button '
        'or send any message with the text – it will be '
        'automatically added as a note to this record.\n\n'
        'If not, simply click the corresponding button.'
    )
    text %= start.strftime('%M, %d, %H:%M:%S'), (end - start), task.name

    if message:
        explanation = await bot.edit_message_text(
            text, **message, reply_markup=markup
        )
    else:
        explanation = await bot.send_message(
            event_from_user.id, text, reply_markup=markup
        )

    data = {'task': task, 'start': start, 'end': end}
    if isinstance(explanation, types.Message):
        data['explanation'] = explanation.chat.id, explanation.message_id

    await state.set_data(data)
    await state.set_state(CreateDuration.typing)


@router.callback_query(
    F.data == link.Call.Task.save_duration, without_state
)
async def stateless_save_duration(callback: types.CallbackQuery, bot: Bot):
    msg = callback.message
    if msg:
        await bot.edit_message_reply_markup(msg.chat.id, msg.message_id)

    await callback.answer(
        _('Sorry, something unexpected happened. I can\'t process it.')
    )


@router.message(
    CreateDuration.typing
)
@router.callback_query(
    CreateDuration.typing, F.data == link.Call.Task.save_duration
)
async def save_duration(
    update: types.Message | types.CallbackQuery,
    bot: Bot,
    state: FSMContext,
    event_from_user: types.User
):
    data = await state.get_data()
    explanation = data.pop('explanation', None)
    is_callback = isinstance(update, types.CallbackQuery)
    notes = None

    try:
        task: Task = data.pop('task')
    except KeyError:
        return await update.answer(
            _('Sorry, something unexpected happened. I can\'t process it.')
        )

    if isinstance(update, types.Message):
        if not update.text:
            return await update.answer(
                _('Sorry, but I can\'t process it. Try again.')
            )
        notes = update.text

    if isinstance(explanation, tuple):
        await bot.edit_message_reply_markup(*explanation)

    try:
        with database:
            Duration.create(validate=True, task=task, notes=notes, **data)
    except ValueError as e:
        text = str(e)

        if is_callback:
            await bot.send_message(event_from_user.id, text)
        return await update.answer(text)

    text = _(
        'The time record for the task "%s" has been successfully created.'
    ) % task.name

    await state.clear()
    await update.answer(text)

    if is_callback:
        await bot.send_message(event_from_user.id, text)


@detail_router.callback_query(
    LinkFilter(link.Call.Task.task_reports)
)
async def task_reports(
    callback: types.CallbackQuery,
    bot: Bot,
    event_from_user: types.User,
    task: Task
):
    text = _(
        'Activity reports for the task "%s". To receive the '
        'report, please click the button for the desired period.'
    ) % task.name
    buttons = (
        ('1️⃣ Today', link.Call.Task.task_day_report),
        ('7️⃣ Last 7 days', link.Call.Task.task_week_report),
        ('3️⃣0️⃣ Last 30 days', link.Call.Task.task_month_report),
        ('⬅️ Back', link.Call.Task.back)
    )

    builder = keyboard.InlineKeyboardBuilder()
    for content, base in buttons:
        builder.button(
            text=content, callback_data=link.build(base, id=task.id)
        )

    builder.adjust(2, 2, 1)
    markup = builder.as_markup()

    if callback.message:
        message = callback.message.chat.id, callback.message.message_id
        await bot.edit_message_text(text, *message, reply_markup=markup)
    else:
        await bot.send_message(event_from_user.id, text, reply_markup=markup)

    await callback.answer(text)


@detail_router.callback_query(
        LinkFilter(link.Call.Task.task_day_report)
)
async def task_day_report(
    callback: types.CallbackQuery,
    bot: Bot,
    event_from_user: types.User,
    task: Task
):
    with tempfile.NamedTemporaryFile(suffix='.png') as file:
        try:
            reports.task.today(task, file)
        except ValueError:
            text = _(
                'Sorry, but there is not enough data to generate the '
                'report. Please use the countdown and try again later.'
            )
            await callback.answer(text)
            return await bot.send_message(event_from_user.id, text)

        text = _(
            'The sent photo contains today\'s '
            'activity report for the task "%s".'
        ) % task.name

        await callback.answer('OK')
        await bot.send_photo(
            event_from_user.id, types.FSInputFile(file.name), caption=text
        )


@detail_router.callback_query(
        LinkFilter(link.Call.Task.task_week_report)
)
async def task_week_report(
    callback: types.CallbackQuery,
    bot: Bot,
    event_from_user: types.User,
    task: Task
):
    with tempfile.NamedTemporaryFile(suffix='.png') as file:
        try:
            reports.task.week(task, file)
        except ValueError:
            text = _(
                'Sorry, but there is not enough data to generate the '
                'report. Please use the countdown and try again later.'
            )
            await callback.answer(text)
            return await bot.send_message(event_from_user.id, text)

        text = _(
            'The sent photo contains the activity report '
            'for the task "%s" for the last 7 days.'
        ) % task.name

        await callback.answer('OK')
        await bot.send_photo(
            event_from_user.id, types.FSInputFile(file.name), caption=text
        )


@detail_router.callback_query(
        LinkFilter(link.Call.Task.task_month_report)
)
async def task_month_report(
    callback: types.CallbackQuery,
    bot: Bot,
    event_from_user: types.User,
    task: Task
):
    with tempfile.NamedTemporaryFile(suffix='.png') as file:
        try:
            reports.task.month(task, file)
        except ValueError:
            text = _(
                'Sorry, but there is not enough data to generate the '
                'report. Please use the countdown and try again later.'
            )
            await callback.answer(text)
            return await bot.send_message(event_from_user.id, text)

        text = _(
            'The sent photo contains the activity report '
            'for the task "%s" for the last 30 days.'
        ) % task.name

        await callback.answer('OK')
        await bot.send_photo(
            event_from_user.id, types.FSInputFile(file.name), caption=text
        )


@detail_router.callback_query(
    LinkFilter(link.Call.Task.back)
)
async def back(
    callback: types.CallbackQuery,
    bot: Bot,
    event_from_user: types.User,
    task: Task
):
    text, markup = base_retrieve(task)

    if callback.message:
        message = callback.message.chat.id, callback.message.message_id
        await bot.edit_message_text(text, *message, reply_markup=markup)
    else:
        await bot.send_message(event_from_user.id, text, reply_markup=markup)


@router.callback_query(
    F.data == link.Call.Task.folder_reports
)
async def folder_reports(
    callback: types.CallbackQuery,
    bot: Bot,
    account: Account,
):
    folder = account.active_folder
    text = _(
        'Activity reports for tasks from the "%s" folder. '
        'To obtain a report, select the desired period and click '
        'the corresponding button.'
    )
    text %= folder.name if folder else _('Main folder')
    buttons = (
        ('1️⃣ Today', link.Call.Task.folder_day_report),
        ('7️⃣ Last 7 days', link.Call.Task.folder_week_report),
        ('3️⃣0️⃣ Last 30 days', link.Call.Task.folder_month_report),
        ('⬅️ Back', link.Call.Task.folder_back)
    )

    builder = keyboard.InlineKeyboardBuilder()
    for content, callback_data in buttons:
        builder.button(text=content, callback_data=callback_data)

    builder.adjust(2, 2, 1)
    markup = builder.as_markup()

    if callback.message:
        message = callback.message.chat.id, callback.message.message_id
        await bot.edit_message_text(text, *message, reply_markup=markup)
    else:
        await bot.send_message(account.id, text, reply_markup=markup)

    await callback.answer(text)


@router.callback_query(F.data == link.Call.Task.folder_back)
async def folder_back(
    callback: types.CallbackQuery, bot: Bot, account: Account
):
    text, markup = create_list(account, 1)
    message = callback.message

    if message:
        await bot.edit_message_text(
            text, message.chat.id, message.message_id, reply_markup=markup
        )
    else:
        await callback.answer('OK')
        await bot.send_message(account.id, text, reply_markup=markup)


async def base_folder_report(
    callback: types.CallbackQuery,
    bot: Bot,
    account: Account,
    function: Callable
):
    folder = account.active_folder

    with tempfile.NamedTemporaryFile(suffix='.png') as file:
        try:
            function(account, folder, file)
        except ValueError:
            text = _(
                'Sorry, but there is not enough data to generate the '
                'report. Please use the countdown and try again later.'
            )
            await callback.answer(text)
            return await bot.send_message(account.id, text)

        text = _(
            'The attached photo contains an '
            'activity report for tasks in the "%s" folder'
        )
        text %= folder.name if folder else _('Main folder')

        await callback.answer('OK')
        await bot.send_photo(
            account.id, types.FSInputFile(file.name), caption=text
        )


@router.callback_query(
    F.data == link.Call.Task.folder_day_report
)
async def folder_day_report(
    callback: types.CallbackQuery,
    bot: Bot,
    account: Account
):
    return await base_folder_report(
        callback, bot, account, reports.folder.today
    )


@router.callback_query(
    F.data == link.Call.Task.folder_week_report
)
async def folder_week_report(
    callback: types.CallbackQuery,
    bot: Bot,
    account: Account
):
    return await base_folder_report(
        callback, bot, account, reports.folder.week
    )


@router.callback_query(
    F.data == link.Call.Task.folder_month_report
)
async def folder_month_report(
    callback: types.CallbackQuery,
    bot: Bot,
    account: Account
):
    return await base_folder_report(
        callback, bot, account, reports.folder.month
    )


@detail_router.callback_query(
    LinkFilter(link.Call.Task.start_reminder)
)
async def start_reminder(
    callback: types.CallbackQuery,
    bot: Bot,
    state: FSMContext,
    event_from_user: types.User,
    task: Task
):
    builder = keyboard.InlineKeyboardBuilder()
    builder.button(text=_('Cancel'), callback_data=link.Call.cancel)
    markup = builder.as_markup()

    head = _(
        'To set a reminder, enter the '
        'date and time in the following format:'
    )
    display_format = _('Y-m-d H:M')  # '%Y-%m-%d %H:%M'
    description = [
        _('Y — year (four digits)'),
        _('m — month (two digits)'),
        _('d — day (two digits)'),
        _('H — hour (24-hour format, two digits)'),
        _('M — minutes (two digits)')
    ]
    note = _(
        'Please note that the reminder will '
        'be created according to your time zone.'
    )
    sections = [head, display_format, '\n'.join(description), note]

    text = '\n\n'.join(sections)

    await state.set_state(CreateReminder.typing)
    await state.set_data({'task': task})

    await bot.send_message(event_from_user.id, text, reply_markup=markup)
    await callback.answer(head)


@router.message(CreateReminder.typing)
async def end_reminder(
    message: types.Message, state: FSMContext, account: Account
):
    process_erorr = _('Sorry, but I can\'t process it. Please try again.')

    if not message.text:
        return await message.reply(process_erorr)

    data = await state.get_data()
    task = data.get('task')

    try:
        date = datetime.strptime(message.text, '%Y-%m-%d %H:%M')
    except ValueError:
        return await message.reply(process_erorr)
    try:
        timezone = pytz.timezone(account.timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        timezone = pytz.timezone('UTC')

    date = timezone.localize(date).astimezone(pytz.utc)
    if date < utc_now():
        return await message.reply(_('The entered time is not valid'))

    if not isinstance(task, Task):
        await state.clear()
        return await message.answer(
            _('Sorry, but something went wrong. Please try again.')
        )

    reminder.run.apply_async(args=(account.id, task.id), eta=date)
    await message.answer(_('Reminder successfully created'))
