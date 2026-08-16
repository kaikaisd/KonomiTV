from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "series" ADD COLUMN "normalized_title" VARCHAR(512) NOT NULL DEFAULT '';
        UPDATE "series" SET "normalized_title" = 'legacy:' || "id" WHERE "normalized_title" = '';
        CREATE UNIQUE INDEX "series_normalized_title" ON "series" ("normalized_title");
        UPDATE "recorded_programs" SET "series_broadcast_period_id" = (
            SELECT MIN("survivor"."id") FROM "series_broadcast_periods" AS "survivor"
            WHERE "survivor"."series_id" = (
                SELECT "duplicate"."series_id" FROM "series_broadcast_periods" AS "duplicate"
                WHERE "duplicate"."id" = "recorded_programs"."series_broadcast_period_id"
            ) AND "survivor"."channel_id" = (
                SELECT "duplicate"."channel_id" FROM "series_broadcast_periods" AS "duplicate"
                WHERE "duplicate"."id" = "recorded_programs"."series_broadcast_period_id"
            )
        ) WHERE "series_broadcast_period_id" IS NOT NULL;
        DELETE FROM "series_broadcast_periods" WHERE "id" NOT IN (
            SELECT MIN("id") FROM "series_broadcast_periods" GROUP BY "series_id", "channel_id"
        );
        CREATE UNIQUE INDEX "series_broadcast_period_unique" ON "series_broadcast_periods" ("series_id", "channel_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "series_broadcast_period_unique";
        DROP INDEX IF EXISTS "series_normalized_title";
        ALTER TABLE "series" DROP COLUMN "normalized_title";
    """
