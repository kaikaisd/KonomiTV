
from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "mirakurun_reservations" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            "channel_id" VARCHAR(255) REFERENCES "channels" ("id") ON DELETE SET NULL,
            "network_id" INT NOT NULL,
            "service_id" INT NOT NULL,
            "event_id" INT NOT NULL DEFAULT -1,
            "title" TEXT NOT NULL,
            "description" TEXT NOT NULL DEFAULT '',
            "genres" JSON NOT NULL DEFAULT '[]',
            "start_time" TIMESTAMP NOT NULL,
            "end_time" TIMESTAMP NOT NULL,
            "recording_start_margin" REAL NOT NULL DEFAULT 0.0,
            "recording_end_margin" REAL NOT NULL DEFAULT 0.0,
            "status" VARCHAR(20) NOT NULL DEFAULT 'Pending',
            "recording_file_path" TEXT,
            "record_settings_json" JSON NOT NULL DEFAULT '{}',
            "comment" TEXT NOT NULL DEFAULT '',
            "created_at" TIMESTAMP NOT NULL,
            "updated_at" TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS "idx_mirakurun_reservations_start_time" ON "mirakurun_reservations" ("start_time");
        CREATE INDEX IF NOT EXISTS "idx_mirakurun_reservations_end_time" ON "mirakurun_reservations" ("end_time");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "mirakurun_reservations";
    """
