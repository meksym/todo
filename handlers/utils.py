import link
from aiogram import types
from models import Task, Folder
from aiogram.utils.i18n import gettext as _
from aiogram.utils.keyboard import InlineKeyboardBuilder


# TODO: fix me

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
    builder = InlineKeyboardBuilder()

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
