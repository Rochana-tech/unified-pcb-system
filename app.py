import os

from integration.api import create_app
from integration.config import Settings

settings = Settings(
    mode="demo",
    database=os.getenv("DATABASE_PATH", "/tmp/manufacturing.sqlite3"),
    correction_seconds=int(os.getenv("CORRECTION_SECONDS", "20")),
    demo_backup=True,
    public_site=False,
)

app = create_app(settings, start_background=False, mqtt_enabled=False)
