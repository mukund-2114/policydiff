from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import PRODUCT_NAME
from app.db.session import get_engine
from app.jobs import open_for_api
from app.routers import auth as auth_router
from app.routers import documents, health, samples
from app.auth import bootstrap_admin
from sqlalchemy.orm import Session


@asynccontextmanager
async def lifespan(_: FastAPI):
    with Session(get_engine()) as db:
        bootstrap_admin(db)
    with open_for_api():
        yield


app = FastAPI(title=f"{PRODUCT_NAME} API", lifespan=lifespan)
app.include_router(health.router, prefix="/api")
app.include_router(auth_router.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(samples.router, prefix="/api")
