from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "encoding_tasks" ADD "cm_output_file_path" TEXT NOT NULL DEFAULT '';
        ALTER TABLE "encoding_tasks" ADD "output_format" VARCHAR(10) NOT NULL DEFAULT 'MP4';
        ALTER TABLE "encoding_tasks" ADD "cm_processing" VARCHAR(20) NOT NULL DEFAULT 'None';
        ALTER TABLE "encoding_tasks" ADD "cm_video_bitrate" VARCHAR(50) NOT NULL DEFAULT '';
        UPDATE "encoding_tasks" SET "cm_processing" = 'Remove' WHERE "cm_removal" = 1;
        ALTER TABLE "encoding_tasks" DROP COLUMN "cm_removal";
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "encoding_tasks" ADD "cm_removal" INT NOT NULL DEFAULT 0;
        UPDATE "encoding_tasks" SET "cm_removal" = 1 WHERE "cm_processing" = 'Remove' OR "cm_processing" = 'SeparateOutput';
        ALTER TABLE "encoding_tasks" DROP COLUMN "cm_processing";
        ALTER TABLE "encoding_tasks" DROP COLUMN "cm_video_bitrate";
        ALTER TABLE "encoding_tasks" DROP COLUMN "output_format";
        ALTER TABLE "encoding_tasks" DROP COLUMN "cm_output_file_path";
    """
