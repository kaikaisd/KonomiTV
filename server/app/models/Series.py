
# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from tortoise import fields
from tortoise.fields import Field as TortoiseField
from tortoise.models import Model as TortoiseModel

from app.schemas import Genre


if TYPE_CHECKING:
    from app.models.SeriesBroadcastPeriod import SeriesBroadcastPeriod


class Series(TortoiseModel):

    # データベース上のテーブル名
    class Meta(TortoiseModel.Meta):
        table: str = 'series'

    id = fields.IntField(pk=True)
    # 表記揺れだけを吸収した完全一致用キー。SeriesIndexer が同一シリーズの判定に使う
    normalized_title = fields.CharField(512, unique=True)
    title = fields.TextField()
    description = fields.TextField()
    genres = cast(TortoiseField[list[Genre]], fields.JSONField(default=[], encoder=lambda x: json.dumps(x, ensure_ascii=False)))  # type: ignore
    # Bangumi の収蔵一覧と照合できた作品だけ、条目概要をローカルへキャッシュする
    ## Bangumi 連携が未設定の環境では常に None のままで、外部への通信も発生しない
    bangumi_subject_id = cast(TortoiseField[int | None], fields.IntField(null=True))
    bangumi_subject_name = cast(TortoiseField[str | None], fields.TextField(null=True))
    bangumi_subject_name_cn = cast(TortoiseField[str | None], fields.TextField(null=True))
    bangumi_subject_summary = cast(TortoiseField[str | None], fields.TextField(null=True))
    bangumi_subject_image_url = cast(TortoiseField[str | None], fields.TextField(null=True))
    broadcast_periods: fields.ReverseRelation[SeriesBroadcastPeriod]
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
