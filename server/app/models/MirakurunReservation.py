
# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal, cast

from tortoise import fields
from tortoise.fields import Field as TortoiseField
from tortoise.models import Model as TortoiseModel

from app.schemas import Genre, RecordSettings


if TYPE_CHECKING:
    from app.models.Channel import Channel


class MirakurunReservation(TortoiseModel):
    """
    Mirakurun バックエンドを使った録画予約を管理するモデル。
    EDCB バックエンドでは EDCB 自身が予約を管理するのに対し、Mirakurun バックエンドでは
    KonomiTV 自身がこのテーブルで予約を管理し、MirakurunRecordingTask が実際の録画を担う。
    """

    # データベース上のテーブル名
    class Meta(TortoiseModel.Meta):
        table: str = 'mirakurun_reservations'

    # 主キー (自動インクリメント)
    id = fields.IntField(pk=True)

    # 予約対象チャンネル (Channel が削除されても予約レコード自体は残すため null=True)
    channel: fields.ForeignKeyNullableRelation[Channel] = \
        fields.ForeignKeyField('models.Channel', related_name=None, null=True, on_delete=fields.SET_NULL)
    # 参照キャッシュ (Channel FK が null になっても番組情報を保持するためのデノーマライズ)
    channel_id: str | None

    # チャンネルのネットワーク ID (Mirakurun サービス ID 計算に利用)
    network_id: fields.Field[int] = fields.IntField()
    # チャンネルのサービス ID (Mirakurun サービス ID 計算に利用)
    service_id: fields.Field[int] = fields.IntField()
    # 番組の EID (番組情報から取得; 手動予約の場合は -1)
    event_id: fields.Field[int] = fields.IntField(default=-1)

    # 番組タイトル (予約登録時点の値を保持)
    title = fields.TextField()
    # 番組説明 (予約登録時点の値を保持)
    description = fields.TextField(default='')
    # 番組ジャンル (JSON 配列として格納)
    genres = cast(TortoiseField[list[Genre]], fields.JSONField(default=[], encoder=lambda x: json.dumps(x, ensure_ascii=False)))  # type: ignore

    # 録画開始時刻 (録画開始マージン適用前の番組本来の開始時刻)
    start_time = fields.DatetimeField(index=True)
    # 録画終了時刻 (録画終了マージン適用前の番組本来の終了時刻)
    end_time = fields.DatetimeField(index=True)

    # 録画開始マージン (秒): 番組開始よりこの秒数だけ早く録画を開始する
    # None の場合はグローバルデフォルト設定に従うが、Mirakurun バックエンドではデフォルト 0 秒とする
    recording_start_margin: fields.Field[float] = fields.FloatField(default=0.0)
    # 録画終了マージン (秒): 番組終了よりこの秒数だけ遅く録画を終了する
    # None の場合はグローバルデフォルト設定に従うが、Mirakurun バックエンドではデフォルト 0 秒とする
    recording_end_margin: fields.Field[float] = fields.FloatField(default=0.0)

    # 予約ステータス
    # - Pending: 録画開始待ち
    # - Recording: 録画中
    # - Completed: 録画完了
    # - Failed: 録画失敗
    # - Cancelled: キャンセル済み
    status = cast(
        TortoiseField[Literal['Pending', 'Recording', 'Completed', 'Failed', 'Cancelled']],
        fields.CharField(20, default='Pending'),
    )

    # 実際に録画されたファイルのパス (録画開始時に設定; 録画前は None)
    recording_file_path = cast(TortoiseField[str | None], fields.TextField(null=True))

    # 録画設定 (JSON として格納; Mirakurun では recording_folders と priority のみ実質的に利用)
    record_settings_json = cast(
        TortoiseField[dict[str, Any]],
        fields.JSONField(default={}, encoder=lambda x: json.dumps(x, ensure_ascii=False)),  # type: ignore
    )

    # コメント (手動で追加した備考など)
    comment = fields.TextField(default='')

    # レコード作成日時
    created_at = fields.DatetimeField(auto_now_add=True)
    # レコード最終更新日時
    updated_at = fields.DatetimeField(auto_now=True)

    def getRecordSettings(self) -> RecordSettings:
        """
        JSON フィールドから RecordSettings オブジェクトを復元する。

        Returns:
            RecordSettings: 録画設定
        """
        if not self.record_settings_json:
            return RecordSettings()
        return RecordSettings.model_validate(self.record_settings_json)

    def setRecordSettings(self, record_settings: RecordSettings) -> None:
        """
        RecordSettings オブジェクトを JSON フィールドに保存する。

        Args:
            record_settings (RecordSettings): 保存する録画設定
        """
        self.record_settings_json = record_settings.model_dump()

    def getMirakurunServiceId(self) -> int:
        """
        Mirakurun が内部で利用する 10 桁のサービス ID を計算して返す。
        NID を 5 桁ゼロ埋め、SID を 5 桁ゼロ埋めして連結した値。

        Returns:
            int: Mirakurun 形式のサービス ID
        """
        return int(str(self.network_id).zfill(5) + str(self.service_id).zfill(5))

    def getEffectiveStartTime(self):
        """
        録画開始マージンを考慮した実際の録画開始時刻を返す。

        Returns:
            datetime: 録画開始時刻 (マージン適用済み)
        """
        from datetime import timedelta
        return self.start_time - timedelta(seconds=self.recording_start_margin)

    def getEffectiveEndTime(self):
        """
        録画終了マージンを考慮した実際の録画終了時刻を返す。

        Returns:
            datetime: 録画終了時刻 (マージン適用済み)
        """
        from datetime import timedelta
        return self.end_time + timedelta(seconds=self.recording_end_margin)
