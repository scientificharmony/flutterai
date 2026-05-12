from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from config import settings
from database import create_db_and_tables
from routers import health, scan, alerts, notifications, pie, holdings
from workers.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Flutter AI", version="3.0.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(scan.router)
app.include_router(alerts.router)
app.include_router(notifications.router)
app.include_router(pie.router)
app.include_router(holdings.router)

if settings.enable_admin_routes:
    from routers import admin

    app.include_router(admin.router)

if settings.is_private_test:
    from routers import test_dashboard

    app.include_router(test_dashboard.router)
