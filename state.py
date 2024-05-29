from aiogram.fsm.state import StatesGroup, State


class CreateTask(StatesGroup):
    typing = State()


class ChangeTimezone(StatesGroup):
    typing = State()


class CreateFolder(StatesGroup):
    typing = State()


class UpdateFolder(StatesGroup):
    typing = State()


class UpdateTask(StatesGroup):
    typing = State()


class CreateDuration(StatesGroup):
    typing = State()


class CreateReminder(StatesGroup):
    typing = State()
