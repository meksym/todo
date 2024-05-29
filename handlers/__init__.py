from . import user
from . import task
from . import folder

from aiogram import Router


router = Router()

router.include_router(user.router)
router.include_router(task.router)
router.include_router(folder.router)
