import sys
import asyncio
import settings
import middleware
from handlers import router
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.utils.i18n import I18n
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application
)


def setup() -> tuple[Bot, Dispatcher]:
    '''
    Sets up and returns instances of Bot and Dispatcher for use
    '''
    i18n = I18n(path=settings.LOCALES_PATH,
                default_locale=settings.LANGUAGE_CODE)
    bot = Bot(settings.TOKEN)

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    dispatcher.update.outer_middleware(middleware.AccountMiddleware())
    dispatcher.update.outer_middleware(middleware.LanguageMiddleware(i18n))

    dispatcher.message.outer_middleware(middleware.CreateTaskOuterMiddleware())

    return bot, dispatcher


async def set_webhook(bot: Bot):
    await bot.set_webhook(
        url=settings.WEBHOOK_URL + settings.WEBHOOK_PATH,
        secret_token=settings.WEBHOOK_SECRET
    )


async def remove_webhook(bot: Bot):
    await bot.set_webhook(url='')


def webhook():
    '''
    Executes the setWebhook method of the Bot API and starts an HTTP
    server according to settings.py file to handle updates from Telegram
    '''
    bot, dispatcher = setup()
    app = web.Application()

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=settings.WEBHOOK_SECRET,
    )

    webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)
    dispatcher.startup.register(set_webhook)

    setup_application(app, dispatcher, bot=bot)

    web.run_app(
        app, host=settings.WEB_SERVER_HOST, port=settings.WEB_SERVER_PORT
    )


def polling():
    bot, dispatcher = setup()

    dispatcher.startup.register(remove_webhook)
    coroutine = dispatcher.start_polling(bot)

    asyncio.run(coroutine)


if __name__ == '__main__':
    if '--webhook' in sys.argv:
        webhook()
    else:
        polling()
