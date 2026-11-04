import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, engine
from .routers import auth, chat, reminders, tasks
from .services.reminder_worker import reminder_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    worker = asyncio.create_task(reminder_loop())
    yield
    worker.cancel()


app = FastAPI(title="Trợ lý AI cá nhân", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (auth.router, tasks.router, reminders.router, chat.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok"}
