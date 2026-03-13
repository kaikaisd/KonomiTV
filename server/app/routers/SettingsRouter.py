
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import ValidationError

from app import logging
from app.config import ClientSettings, Config, ReadCurrentConfig, SaveConfig, ServerSettings
from app.models.User import User
from app.routers.UsersRouter import GetCurrentAdminUser, GetCurrentUser
from app.utils.TelegramNotifier import TelegramNotifier


# ルーター
router = APIRouter(
    tags = ['Settings'],
    prefix = '/api/settings',
)


@router.get(
    '/client',
    summary = 'クライアント設定取得 API',
    response_description = 'ログイン中のユーザーアカウントのクライアント設定。',
    response_model = ClientSettings,
)
async def ClientSettingsAPI(
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    現在ログイン中のユーザーアカウントのクライアント設定を取得する。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されていないとアクセスできない。
    """
    return current_user.client_settings


@router.put(
    '/client',
    summary = 'クライアント設定更新 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def ClientSettingsUpdateAPI(
    client_settings: Annotated[ClientSettings, Body(description='更新するクライアント設定のデータ。')],
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    現在ログイン中のユーザーアカウントのクライアント設定を更新する。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されていないとアクセスできない。
    """

    # 現在サーバーに保存されているクライアント設定の最終同期時刻よりも古いクライアント設定が送られてきた場合、エラーを返す
    current_client_settings = ClientSettings.model_validate(current_user.client_settings)
    if client_settings.last_synced_at < current_client_settings.last_synced_at:
        logging.error(f'[ClientSettingsUpdateAPI] Client settings are outdated! [{client_settings.last_synced_at} < {current_client_settings.last_synced_at}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'The client settings are outdated. Please update the client settings from the server.',
        )

    # dict に変換してから入れる
    ## Pydantic モデルのままだと JSON にシリアライズできないので怒られる
    current_user.client_settings = dict(client_settings)

    # レコードを保存する
    await current_user.save()


@router.get(
    '/server',
    summary = 'サーバー設定取得 API',
    response_description = '現在稼働中の KonomiTV サーバーのサーバー設定。',
    response_model = ServerSettings,
)
async def ServerSettingsAPI():
    """
    現在稼働中の KonomiTV サーバーのサーバー設定を取得する。<br>
    Docker 環境では、パス指定の項目は Docker 環境向けの Prefix (/host-rootfs) が付与された状態で返される。<br>
    """

    # SaveConfig() はディスクのみ更新し、インメモリの _CONFIG は更新しないため、
    # 設定保存後すぐにページをリロードしても最新値が反映されるよう ReadCurrentConfig() を使う
    return ReadCurrentConfig()


@router.put(
    '/server',
    summary = 'サーバー設定更新 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def ServerSettingsUpdateAPI(
    server_settings_raw: Annotated[dict[str, Any], Body(description='更新するサーバー設定のデータ。')],
    current_user: Annotated[User, Depends(GetCurrentAdminUser)],
):
    """
    現在稼働中の KonomiTV サーバーのサーバー設定を更新する。<br>
    Docker 環境では、パス指定の項目には Docker 環境向けの Prefix (/host-rootfs) を付与した状態でリクエストする必要がある。<br>
    バックエンド (EDCB/Mirakurun) への接続確認はサーバー起動時に実施済みのためスキップする。<br>
    接続確認のブロッキング処理が不要になった分、レスポンスが高速化される。<br>

    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されていて、かつ管理者アカウントでないとアクセスできない。
    """

    # バックエンド接続確認をスキップしてバリデーションを実行する
    # 接続確認 (EDCB/Mirakurun の疎通確認) はサーバー起動時に一度実施済みであり、
    # 設定更新時に再度実行するとバックエンドが一時停止中の場合に設定を保存できなくなるため、スキップする
    try:
        server_settings = ServerSettings.model_validate(
            server_settings_raw,
            context = {'bypass_validation': True},
        )
    except ValidationError as error:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = str(error),
        )

    # バリデーションが完了したサーバー設定を config.yaml に保存する
    SaveConfig(server_settings)


@router.post(
    '/notification/test',
    summary = 'Telegram テスト通知送信 API',
    response_description = 'テスト通知の送信結果。',
)
async def TestTelegramNotificationAPI(
    current_user: Annotated[User, Depends(GetCurrentUser)],
) -> dict[str, str]:
    """
    現在の Telegram 通知設定を使ってテストメッセージを送信する。<br>
    設定が正しく動作するかどうかを確認するために使用する。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されていないとアクセスできない。
    """

    # Config() はサーバー起動時に読み込んだインメモリの設定を返すが、SaveConfig() は config.yaml のみ更新し
    # インメモリ設定を更新しないため、保存直後にテストを実行すると古い設定が参照される問題がある
    # ReadCurrentConfig() は毎回 config.yaml を読み直すため、再起動なしに最新の設定を参照できる
    cfg = ReadCurrentConfig().notification

    # Telegram 通知が無効の場合はエラーを返す
    if not cfg.telegram_notification_enabled:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = 'Telegram notifications are not enabled. Please enable them in server settings first.',
        )

    # Bot トークンまたはチャット ID が未設定の場合はエラーを返す
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = 'Telegram bot token or chat ID is not configured.',
        )

    # テスト通知を送信する
    success = await TelegramNotifier.sendTestNotification(
        bot_token = cfg.telegram_bot_token,
        chat_id = cfg.telegram_chat_id,
    )
    if not success:
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = 'Failed to send test notification. Please check your bot token and chat ID.',
        )

    return {'detail': 'Test notification sent successfully.'}
