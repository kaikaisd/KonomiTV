
# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal, cast

from tortoise import fields
from tortoise.fields import Field as TortoiseField
from tortoise.models import Model as TortoiseModel


if TYPE_CHECKING:
    from app.models.RecordedVideo import RecordedVideo


class EncodingTask(TortoiseModel):
    """
    バッチエンコードタスクを管理するモデル。
    Amatsukaze のキューシステムに着想を得て、録画 TS ファイルの MP4 へのバッチトランスコードを管理する。
    EncodingQueueManager がバックグラウンドでこのテーブルを監視し、Pending タスクを順次エンコードする。
    """

    # データベース上のテーブル名
    class Meta(TortoiseModel.Meta):
        table: str = 'encoding_tasks'

    # 主キー (自動インクリメント)
    id = fields.IntField(pk=True)

    # ***** 入出力パス *****

    # エンコード元の録画 TS ファイルのパス
    source_file_path = fields.TextField()
    # エンコード後の出力ファイルパス (エンコード開始時に EncodingQueueManager が設定する)
    output_file_path = fields.TextField(default='')

    # 録画番組 (RecordedVideo) との関連 (任意: 録画番組が削除されてもタスクレコードは残す)
    recorded_video: fields.ForeignKeyNullableRelation[RecordedVideo] = \
        fields.ForeignKeyField('models.RecordedVideo', related_name=None, null=True, on_delete=fields.SET_NULL)
    recorded_video_id: int | None

    # ***** エンコード設定 *****

    # 使用するエンコーダーの種別
    encoder_type = cast(
        TortoiseField[Literal['FFmpeg', 'QSVEncC', 'NVEncC', 'VCEEncC', 'rkmppenc']],
        fields.CharField(20, default='FFmpeg'),
    )
    # 出力映像コーデック
    video_codec = cast(
        TortoiseField[Literal['H.264', 'H.265']],
        fields.CharField(10, default='H.264'),
    )
    # エンコーダー固有のプリセット名 (例: 'medium', 'fast', 'slow')
    quality_preset = fields.CharField(50, default='medium')
    # 映像ビットレート (例: '4000k')
    video_bitrate = fields.CharField(50, default='4000k')
    # 音声ビットレート (例: '192k')
    audio_bitrate = fields.CharField(50, default='192k')

    # CM 区間を除去するかどうか (検出済みの CM 区間情報を利用して、CM 部分をカットしてエンコードする)
    cm_removal = fields.BooleanField(default=False)

    # ***** 状態管理 *****

    # エンコードタスクのステータス
    # - Pending: エンコード待ち (キューに積まれた状態)
    # - Encoding: エンコード中
    # - Completed: エンコード完了
    # - Failed: エンコード失敗
    # - Cancelled: ユーザーによりキャンセルされた
    status = cast(
        TortoiseField[Literal['Pending', 'Encoding', 'Completed', 'Failed', 'Cancelled']],
        fields.CharField(20, default='Pending', db_index=True),
    )
    # タスクの優先度 (数値が大きいほど優先度が高い。デフォルト 0 = 通常)
    priority = fields.IntField(default=0)
    # エンコード進捗率 (0.0 ~ 100.0)
    ## EncodingQueueManager がエンコーダーの出力をパースして定期的に更新する
    progress = fields.FloatField(default=0.0)
    # 失敗時のエラーメッセージ (失敗していない場合は空文字列)
    fail_reason = fields.TextField(default='')

    # ***** 時刻情報 *****

    # タスクがキューに追加された日時
    added_at = fields.DatetimeField(auto_now_add=True)
    # エンコードが開始された日時 (エンコード前は None)
    encoding_started_at = cast(TortoiseField[datetime | None], fields.DatetimeField(null=True))
    # エンコードが完了/失敗した日時 (エンコード完了/失敗前は None)
    encoding_finished_at = cast(TortoiseField[datetime | None], fields.DatetimeField(null=True))
    # レコード作成日時
    created_at = fields.DatetimeField(auto_now_add=True)
    # レコード最終更新日時
    updated_at = fields.DatetimeField(auto_now=True)
