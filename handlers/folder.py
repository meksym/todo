import link
from models import database, Account, Folder
from state import CreateFolder, UpdateFolder

from math import ceil
from peewee import DoesNotExist

from aiogram import Router, Bot, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils import keyboard
from aiogram.utils.i18n import gettext as _
from aiogram.utils.formatting import Text, as_numbered_section


router = Router()


def get_list(account: Account,
             page: int) -> tuple[Text, types.InlineKeyboardMarkup | None]:

    builder = keyboard.InlineKeyboardBuilder()

    with database:
        count = account.folders.count()  # type: ignore

        if not count:
            text = _(
                "Sorry, but I can't show the "
                "folders because you don't have them."
            )
            builder.button(
                text=_('🆕 Create folder'),
                callback_data=link.Callback.folder_create
            )
            return Text(text), builder.as_markup()

        per_page = 10
        pages = ceil(count / per_page)

        if page > pages or page < 0:
            return Text('Incorrect page'), None

        folders = account.folders.paginate(page, per_page)
        folders = list(folders)  # type: ignore

    if page == 1:
        folders.insert(
            0, Folder(id=0, name=_('Main folder'))
        )

    for number, folder in enumerate(folders, 1):
        builder.button(
            text=str(number),
            callback_data=f'{link.Callback.folder_retrieve}/{folder.id}'
        )

    pagination = 0

    if page > 1:
        builder.button(
            text=_('⬅️ Previous page'),
            callback_data=f'{link.Callback.folder_list_page}/{page - 1}'
        )
        pagination += 1
    if page < pages:
        builder.button(
            text=_('➡️ Next page'),
            callback_data=f'{link.Callback.folder_list_page}/{page + 1}'
        )
        pagination += 1

    builder.button(
        text=_('🆕 Create new'),
        callback_data=link.Callback.folder_create
    )

    length = len(folders)
    rows = length // 5
    remainder = length % 5
    sheet = rows * [5]

    if rows and remainder == 1:
        sheet[-1] += remainder
    elif remainder:
        sheet.append(remainder)
    if pagination:
        sheet.append(pagination)
    sheet.append(1)

    builder.adjust(*sheet)

    title = _(
        'Below is a list of your folders. '
        'To change the folder, click on the corresponding number.\n'
    )
    text = as_numbered_section(title, *folders)

    return text, builder.as_markup()


@router.callback_query(
    F.data.startswith(link.Callback.folder_list_page)
)
async def paginated_listing(
    callback: types.CallbackQuery, bot: Bot, account: Account
):
    page = callback.data.split('/')[-1]  # type: ignore

    if not page.isdigit():
        return await callback.answer('Incorrect page')

    text, markup = get_list(account, int(page))

    if callback.message:
        chat, message = callback.message.chat.id, callback.message.message_id

        await bot.edit_message_text(
            chat_id=chat, message_id=message, **text.as_kwargs()
        )
        await bot.edit_message_reply_markup(
            chat_id=chat, message_id=message, reply_markup=markup
        )
    else:
        await bot.send_message(
            account.id,  # type: ignore
            **text.as_kwargs(),
            reply_markup=markup
        )


@router.callback_query(
    F.data == link.Callback.folder_list
)
async def listing_as_callback(
    callback: types.CallbackQuery, bot: Bot, account: Account
):
    text, markup = get_list(account, 1)

    if callback.message:
        chat, message = callback.message.chat.id, callback.message.message_id

        await bot.edit_message_text(
            chat_id=chat, message_id=message, **text.as_kwargs()
        )
        await bot.edit_message_reply_markup(
            chat_id=chat, message_id=message, reply_markup=markup
        )
    else:
        await bot.send_message(
            account.id, **text.as_kwargs(), reply_markup=markup  # type: ignore
        )


@router.message(F.text == link.Text.folders)
@router.message(
    Command(link.Cmd.folders)
)
async def listing_as_message(
    message: types.Message, bot: Bot, account: Account
):
    text, markup = get_list(account, 1)
    await message.answer(**text.as_kwargs(), reply_markup=markup)


@router.callback_query(F.data == link.Callback.folder_create)
async def create(callback: types.CallbackQuery,
                 bot: Bot,
                 state: FSMContext,
                 account: Account):

    builder = keyboard.InlineKeyboardBuilder()
    builder.button(text=_('⬅️ Cancel'), callback_data=link.Callback.cancel)

    text = _(
        'Creating a new folder. You need to enter a name, and if '
        'necessary, you can enter a description on the next line.'
    )

    await state.set_state(
        CreateFolder.typing
    )
    await bot.send_message(
        chat_id=account.id,  # type: ignore
        text=text,
        reply_markup=builder.as_markup()
    )
    await callback.answer(text)


@router.message(CreateFolder.typing)
async def save(
    message: types.Message, bot: Bot, state: FSMContext, account: Account
):
    if not message.text:
        await message.reply(_("Sorry, but I can't process it. Try again."))
        return await create(None, bot, state, account)

    data = message.text.split('\n\n', 1)
    name, description = data if len(data) == 2 else (data[0], None)

    with database:
        Folder.create(
            name=name,
            account=account,
            description=description
        )

    text = _(
        'Folder "%s" has been created. '
        'Type /%s to view the list of folders.'
    )
    text = text % (name, link.Cmd.folders.command)

    await state.set_state(None)
    await message.answer(text)


@router.callback_query(
    F.data.startswith(link.Callback.folder_retrieve)
)
async def retrieve(
    callback: types.CallbackQuery, bot: Bot, account: Account
):
    does_not_exists = _('Folder does not exists')

    try:
        id = int(callback.data.split('/')[-1])  # type: ignore
    except ValueError:
        return await callback.answer(does_not_exists)

    if id == 0:
        folder = Folder(
            id=0,
            name=_('Main folder'),
            description=_(
                'This is the main folder that always '
                'exists by default and cannot be deleted or edited.'
            )
        )
    else:
        try:
            with database:
                filter = Folder.id == id  # type: ignore
                folder = account.folders.where(filter).get()  # type: ignore
        except DoesNotExist:
            return await callback.answer(does_not_exists)

    builder = keyboard.InlineKeyboardBuilder()

    builder.button(
        text=_('🟢 Set as active'),
        callback_data=f'{link.Callback.set_active_folder}/{id}'
    )
    builder.button(
        text=_('🔄 Update details'),
        callback_data=f'{link.Callback.folder_update}/{id}'
    )
    builder.button(
        text=_('❌ Delete'),
        callback_data=f'{link.Callback.folder_delete}/{id}'
    )
    builder.button(
        text=_('📁 Folders'),
        callback_data=link.Callback.folder_list
    )
    builder.adjust(1, 2, 1)

    markup = builder.as_markup()

    if folder.description:
        text = _(
            'Folder:\n\n'
            '{name}\n\n'
            '{description}'
        )
        text = text.format(name=folder.name, description=folder.description)
    else:
        text = _('Folder:\n\n%s') % folder.name

    if callback.message:
        chat, message = callback.message.chat.id, callback.message.message_id

        await bot.edit_message_text(
            text, chat_id=chat, message_id=message
        )
        await bot.edit_message_reply_markup(
            chat_id=chat, message_id=message, reply_markup=markup
        )
    else:
        await bot.send_message(
            account.id, text, reply_markup=markup  # type: ignore
        )


@router.callback_query(
    F.data.startswith(link.Callback.set_active_folder)
)
async def activate(
    callback: types.CallbackQuery, account: Account, bot: Bot
):
    does_not_exists = _('Folder does not exists')

    try:
        folder_id = int(callback.data.split('/')[-1])  # type: ignore
    except (ValueError, DoesNotExist):
        return await callback.answer(does_not_exists)

    with database:
        if folder_id == 0:
            folder = None
        else:
            try:
                filter = Folder.id == folder_id  # type: ignore
                folder = account.folders.where(filter).get()  # type: ignore
            except DoesNotExist:
                return await callback.answer(does_not_exists)

        account.active_folder = folder  # type: ignore
        account.save()

    name = folder.name if folder else _('Main folder')
    text = _('Active folder successfully changed. Now active folder is "%s"')
    text %= name

    await callback.answer(text)
    await bot.send_message(account.id, text)   # type: ignore


@router.callback_query(
    F.data.startswith(link.Callback.folder_update)
)
async def update(callback: types.CallbackQuery,
                 bot: Bot,
                 state: FSMContext,
                 account: Account):
    does_not_exists = _('Folder does not exists')

    try:
        folder_id = int(callback.data.split('/')[-1])  # type: ignore
    except (ValueError, DoesNotExist):
        return await callback.answer(does_not_exists)

    if folder_id == 0:
        return await callback.answer(
            _('Sorry, but you cannot change the data of the main folder.')
        )
    else:
        try:
            with database:
                filter = Folder.id == folder_id  # type: ignore
                folder = account.folders.where(filter).get()  # type: ignore
        except DoesNotExist:
            return await callback.answer(does_not_exists)

    text = _(
        'To change the "%s" folder, you need to send me '
        'a new name and if necessary a description via line'
    )
    text %= folder.name

    builder = keyboard.InlineKeyboardBuilder()
    builder.button(text=_('⬅️ Cancel'), callback_data=link.Callback.cancel)

    message = await bot.send_message(
        account.id,  # type: ignore
        text,
        reply_markup=builder.as_markup()
    )

    await state.set_state(UpdateFolder.typing)
    await state.set_data({
        'folder_id': folder.id,
        'chat_id': message.chat.id,
        'message_id': message.message_id
    })


@router.message(UpdateFolder.typing)
async def save_update(
    message: types.Message, bot: Bot, state: FSMContext, account: Account
):
    data = await state.get_data()
    id = data.pop('folder_id', None)

    if not message.text:
        return await message.reply(
            _("Sorry, but I can't process it. Try again.")
        )
    if not isinstance(id, int):
        return await message.answer('Incorrect id ):')

    with database:
        try:
            filter = Folder.id == id  # type: ignore
            folder = account.folders.where(filter).get()  # type: ignore
        except DoesNotExist:
            return await message.answer(_('Folder does not exist'))

        input = message.text.split('\n\n', 1)
        name, description = input if len(input) == 2 else (input[0], None)

        folder.name = name
        if description:
            folder.description = description
        folder.save()

    text = _(
        'Folder "%s" successfully changed. '
        'Type /%s to view the list of folders.'
    )
    text = text % (name, link.Cmd.folders.command)

    if 'message_id' in data and 'chat_id' in data:
        await bot.edit_message_reply_markup(**data)

    await state.clear()
    await message.answer(text)


@router.callback_query(
    F.data.startswith(link.Callback.folder_delete)
)
async def delete(
    callback: types.CallbackQuery,
    bot: Bot,
    account: Account,
    state: FSMContext
):
    does_not_exists = _('Folder does not exists')

    try:
        id = int(callback.data.split('/')[-1])  # type: ignore
    except (ValueError, DoesNotExist):
        return await callback.answer(does_not_exists)

    if id == 0:
        return await callback.answer(
            _('Sorry, but you cannot delete the main folder.')
        )

    builder = keyboard.InlineKeyboardBuilder()
    builder.button(
        text=_('❌ Confirm deletion'),
        callback_data=f'{link.Callback.folder_perform_delete}/{id}'
    )
    builder.button(
        text=_('⬅️ Cancel'),
        callback_data=link.Callback.folder_cancel_delete
    )

    text = _(
        'Are you sure you want to delete this folder? '
        'If you delete it, all its contents will also be deleted.'
    )
    if callback.message:
        data = {
            'chat_id': callback.message.chat.id,
            'message_id': callback.message.message_id
        }
        await state.set_data(data)

    await callback.answer(text)
    await bot.send_message(
        account.id,  # type: ignore
        text,
        reply_markup=builder.as_markup()
    )


@router.callback_query(
    F.data.startswith(link.Callback.folder_perform_delete)
)
async def perform_delete(
    callback: types.CallbackQuery,
    bot: Bot,
    account: Account,
    state: FSMContext
):
    does_not_exists = _('Folder does not exists')

    try:
        id = int(callback.data.split('/')[-1])  # type: ignore
    except (ValueError, DoesNotExist):
        return await callback.answer(does_not_exists)

    if id == 0:
        return await callback.answer(
            _('Sorry, but you cannot delete the main folder.')
        )

    with database:
        try:
            filter = Folder.id == id  # type: ignore
            folder = account.folders.where(filter).get()  # type: ignore
        except DoesNotExist:
            return await callback.answer(does_not_exists)

        if account.active_folder == folder:
            account.active_folder = None  # type: ignore
            account.save()

        folder.delete_instance()

    text = _('Folder "%s" was successfully deleted') % folder.name
    data = await state.get_data()

    if 'chat_id' in data and 'message_id' in data:
        await bot.edit_message_reply_markup(**data)

    if callback.message:
        await bot.edit_message_text(
            text, callback.message.chat.id, callback.message.message_id
        )

    await callback.answer(text)


@router.callback_query(
    F.data == link.Callback.folder_cancel_delete
)
async def cancel_delete(
    callback: types.CallbackQuery, bot: Bot, account: Account
):
    if callback.message:
        await bot.delete_message(
            callback.message.chat.id, callback.message.message_id
        )

    await callback.answer(_('Okey'))
