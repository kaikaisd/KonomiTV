
from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "mirakurun_recording_rules" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            "program_search_condition_json" TEXT NOT NULL DEFAULT '{}',
            "record_settings_json" TEXT NOT NULL DEFAULT '{}',
            "created_at" TIMESTAMP NOT NULL,
            "updated_at" TIMESTAMP NOT NULL
        );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "mirakurun_recording_rules";
    """
