from urllib.parse import urlparse, parse_qs

from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject, CallbackQuery


async def without_state(update: TelegramObject, state: FSMContext):
    return (await state.get_state() is None)


class LinkFilter(Filter):
    '''
    Establishes a connection with the link provided during
    initialization and adds the parameters of this link to
    the request context
    '''

    def __init__(self, link: str) -> None:
        # Link without query parameters
        self.link = link

    async def __call__(self, callback: CallbackQuery):
        data = callback.data or ''

        if data.startswith(self.link):
            params = parse_qs(urlparse(data).query)

            for key, values in params.items():
                if len(values) == 1:
                    value = values[0]

                    if value.isdigit():
                        value = int(value)

                    params[key] = value  # type: ignore

            return {'params': params}
        else:
            return False
