
from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "encoding_tasks" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            "source_file_path" TEXT NOT NULL,
            "output_file_path" TEXT NOT NULL DEFAULT '',
            "encoder_type" VARCHAR(20) NOT NULL DEFAULT 'FFmpeg',
            "video_codec" VARCHAR(10) NOT NULL DEFAULT 'H.264',
            "quality_preset" VARCHAR(50) NOT NULL DEFAULT 'medium',
            "video_bitrate" VARCHAR(50) NOT NULL DEFAULT '4000k',
            "audio_bitrate" VARCHAR(50) NOT NULL DEFAULT '192k',
            "status" VARCHAR(20) NOT NULL DEFAULT 'Pending',
            "priority" INT NOT NULL DEFAULT 0,
            "progress" REAL NOT NULL DEFAULT 0.0,
            "fail_reason" TEXT NOT NULL DEFAULT '',
            "added_at" TIMESTAMP NOT NULL,
            "encoding_started_at" TIMESTAMP,
            "encoding_finished_at" TIMESTAMP,
            "created_at" TIMESTAMP NOT NULL,
            "updated_at" TIMESTAMP NOT NULL,
            "recorded_video_id" INT REFERENCES "recorded_videos" ("id") ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS "idx_encoding_tasks_status" ON "encoding_tasks" ("status");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "encoding_tasks";
    """
