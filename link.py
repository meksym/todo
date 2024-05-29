'''
The module contains static classes
representing links to various resources and actions
'''

from aiogram import types
from urllib.parse import urlencode


def build(link: str, **kwargs):
    return link + '?' + urlencode(kwargs)


class Command:
    start = types.BotCommand(command='start', description='Start')
    create = types.BotCommand(command='create', description='Create task')
    list = types.BotCommand(command='list', description='To-do list')
    folders = types.BotCommand(command='folders', description='To-do list')
    settings = types.BotCommand(command='settings', description='Settings')
    help = types.BotCommand(command='help', description='How it works?')


class Text:
    help = 'How it works❓'
    list = '📝 To-do list'
    create = '🆕 Create task'
    settings = '⚙️ Settings'
    folders = '📁 Folders'


class Callback:
    # Must be 1-64 bytes

    cancel = 'cancel'
    back_to_settings = 'back-to-settings'

    change_active_folder = 'change-active-folder'
    change_timezone = 'change-timezone'
    change_language = 'change-language'
    set_language = 'set-language'

    folder_list = 'folder-list'
    folder_list_page = 'folder-list-page'
    folder_retrieve = 'folder-retrieve'
    folder_create = 'folder-create'
    folder_update = 'folder-update'
    folder_delete = 'folder-delete'
    folder_perform_delete = 'folder-perform-delete'
    folder_cancel_delete = 'folder-cancel-delete'
    set_active_folder = 'set-active-folder'

    class Folder:
        ...

    class Task:
        list = 'task-list'
        retrieve = 'task-retrieve'
        create = 'task-create'
        _end_create = 'task-end-create'
        update = 'task-update'
        remove = 'task-remove'
        confirm_remove = 'task-confirm-remove'
        start_countdown = 'task-start-countdown'
        complete_countdown = 'end'
        save_duration = 'task-save-duration'
        mark_done = 'task-mark-done'
        task_reports = 'task-reports'
        back = 'back'
        task_day_report = 'task-day-report'
        task_week_report = 'task-week-report'
        task_month_report = 'task-month-report'
        folder_reports = 'folder-reports'
        folder_back = 'folder-back'
        folder_day_report = 'folder-day-report'
        folder_week_report = 'folder-week-report'
        folder_month_report = 'folder-month-report'
        start_reminder = 'start-reminder'


Cmd = Command
Call = Callback
