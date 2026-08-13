
from tortoise import fields
from tortoise.models import Model as TortoiseModel

from app.models.User import User


class DeviceAuth(TortoiseModel):
    """
    テレビ向けクライアントなど、文字入力が困難な端末を KonomiTV アカウントへ紐付けるための一時的なペアリング要求を管理するモデル
    OAuth 2.0 Device Authorization Grant と同じ流れで、端末側はデバイスコードを保持し、ユーザーはブラウザ上でユーザーコードを承認する
    """

    class Meta(TortoiseModel.Meta):
        table = 'device_auth'

    id = fields.IntField(pk=True)
    # 端末だけが保持するデバイスコードの SHA-256 ハッシュ (平文は DB に保存しない)
    device_code_hash = fields.CharField(max_length=64, unique=True)
    # ユーザーが画面上で読み上げて入力する短いコード
    user_code = fields.CharField(max_length=8, unique=True)
    # 連携元端末の表示名 (どの端末を承認しようとしているかをユーザーに提示するために使う)
    device_name = fields.TextField()
    # 承認したユーザー (未承認の間は None のままとなる)
    # ユーザー削除時は承認済みのペアリング要求も無効になるため cascade で削除する
    user: fields.ForeignKeyNullableRelation[User] = \
        fields.ForeignKeyField('models.User', related_name=None, null=True, on_delete=fields.CASCADE)
    user_id: int | None
    expires_at = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)
