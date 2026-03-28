
from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "encoding_tasks" ADD COLUMN "cm_removal" INT NOT NULL DEFAULT 0;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "encoding_tasks" DROP COLUMN "cm_removal";
    """
