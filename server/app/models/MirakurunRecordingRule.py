
# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

import json

from tortoise import fields
from tortoise.models import Model as TortoiseModel

from app import schemas


class MirakurunRecordingRule(TortoiseModel):
    """
    Mirakurun バックエンドのキーワード自動予約条件 (録画ルール) モデル。
    schemas.ProgramSearchCondition を JSON で保存し、定期的に番組 DB をスキャンして
    マッチした番組に対して MirakurunReservation を自動生成するための条件を保持する。

    各ルールの is_enabled / keyword / note は ProgramSearchCondition の中に含まれており、
    program_search_condition_json から取り出して参照する。
    """

    # データベース上のテーブル名
    class Meta(TortoiseModel.Meta):
        table: str = 'mirakurun_recording_rules'

    # 自動インクリメントの主キー
    id = fields.IntField(pk=True)

    # 番組検索条件 (schemas.ProgramSearchCondition の全フィールドを JSON シリアライズして保存する)
    ## is_enabled / keyword / note などの検索パラメータを全て含む
    program_search_condition_json = fields.TextField(default='{}')

    # 録画設定 (schemas.RecordSettings の全フィールドを JSON シリアライズして保存する)
    ## priority / recording_start_margin / recording_end_margin などの録画パラメータを全て含む
    record_settings_json = fields.TextField(default='{}')

    # 作成日時 (auto_now_add=True で自動設定)
    created_at = fields.DatetimeField(auto_now_add=True)
    # 更新日時 (auto_now=True でレコード更新ごとに自動更新)
    updated_at = fields.DatetimeField(auto_now=True)

    def getProgramSearchCondition(self) -> schemas.ProgramSearchCondition:
        """
        JSON から schemas.ProgramSearchCondition オブジェクトを取得する。
        デシリアライズに失敗した場合はデフォルト値で初期化したオブジェクトを返す。

        Returns:
            schemas.ProgramSearchCondition: 番組検索条件
        """
        try:
            data = json.loads(self.program_search_condition_json)
            return schemas.ProgramSearchCondition(**data)
        except Exception:
            return schemas.ProgramSearchCondition()

    def setProgramSearchCondition(self, condition: schemas.ProgramSearchCondition) -> None:
        """
        schemas.ProgramSearchCondition オブジェクトを JSON に変換して保存する。

        Args:
            condition (schemas.ProgramSearchCondition): 番組検索条件
        """
        self.program_search_condition_json = condition.model_dump_json()

    def getRecordSettings(self) -> schemas.RecordSettings:
        """
        JSON から schemas.RecordSettings オブジェクトを取得する。
        デシリアライズに失敗した場合はデフォルト値で初期化したオブジェクトを返す。

        Returns:
            schemas.RecordSettings: 録画設定
        """
        try:
            data = json.loads(self.record_settings_json)
            return schemas.RecordSettings(**data)
        except Exception:
            return schemas.RecordSettings()

    def setRecordSettings(self, settings: schemas.RecordSettings) -> None:
        """
        schemas.RecordSettings オブジェクトを JSON に変換して保存する。

        Args:
            settings (schemas.RecordSettings): 録画設定
        """
        self.record_settings_json = settings.model_dump_json()
