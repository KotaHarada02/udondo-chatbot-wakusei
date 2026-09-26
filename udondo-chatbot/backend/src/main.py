"""FastAPI の入口。見本の無料版の接客 bot の API を載せる。"""

import logging

from fastapi import FastAPI

from src.bot.api import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(title="Udondo Bot API", version="0.3.0")
    app.include_router(router)
    return app


app = create_app()
