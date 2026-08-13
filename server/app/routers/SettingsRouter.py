
import asyncio
import html as html_module
import weakref
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError

from app import logging, schemas
from app.config import (
    ClientSettings,
    ReadCurrentConfig,
    SaveConfig,
    ServerSettings,
)
from app.models.User import User
from app.routers.UsersRouter import GetCurrentAdminUser, GetCurrentUser
from app.utils.TelegramNotifier import TelegramNotifier
from app.WatchedHistory import MergeWatchedHistory


# ルーター
router = APIRouter(
    tags = ['Settings'],
    prefix = '/api/settings',
)

# client_settings は JSON カラムのため、同一ユーザーへの並行更新を直列化して read-modify-write の取りこぼしを防ぐ
## WeakValueDictionary により、更新が終わって参照されなくなったユーザーのロックは自動的に解放される
__client_settings_update_locks: weakref.WeakValueDictionary[int, asyncio.Lock] = weakref.WeakValueDictionary()


def GetClientSettingsUpdateLock(user_id: int) -> asyncio.Lock:
    """
    ユーザー単位でクライアント設定更新を直列化するためのロックを取得する。

    Args:
        user_id (int): 更新対象ユーザーの ID 。

    Returns:
        asyncio.Lock: 指定ユーザーに対応する更新ロック。
    """

    lock = __client_settings_update_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        __client_settings_update_locks[user_id] = lock
    return lock


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

    # 視聴履歴専用 API と通常の設定同期が同時に走っても、どちらか一方の更新を失わないよう直列化する
    lock = GetClientSettingsUpdateLock(current_user.id)
    async with lock:
        # ロック待ちの間に他のリクエストが client_settings を更新している可能性があるため、最新の値を読み直す
        await current_user.refresh_from_db(fields=['client_settings'])

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
        updated_settings = dict(client_settings)

        # 視聴履歴だけは設定全体の上書きではなく、録画番組ごとの最終更新時刻を基準にマージする
        ## 複数端末から設定同期が行われた際に、他の端末で進んだ再生位置を巻き戻さないようにするため
        updated_settings['watched_history'] = MergeWatchedHistory(
            current_client_settings.watched_history,
            client_settings.watched_history,
            client_settings.video_watched_history_max_count,
        )
        current_user.client_settings = updated_settings

        # レコードを保存する
        await current_user.save()


@router.get(
    '/client/watched-history',
    summary = '視聴履歴取得 API',
    response_description = 'ログイン中のユーザーアカウントの視聴履歴。',
    response_model = schemas.WatchedHistory,
)
async def WatchedHistoryAPI(
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    ログイン中ユーザーの視聴履歴を取得する。<br>
    クライアント設定全体を取得せずに視聴履歴だけを同期したい端末向けの API 。

    Args:
        current_user (User): JWT から解決したログイン中のユーザー。

    Returns:
        schemas.WatchedHistory: サーバーに保存されている視聴履歴。
    """

    client_settings = ClientSettings.model_validate(current_user.client_settings)
    # client_settings.watched_history は JSON カラム由来の dict のリストなので、スキーマへ明示的に変換する
    return schemas.WatchedHistory(
        items = [schemas.WatchedHistoryItem.model_validate(item) for item in client_settings.watched_history],
    )


@router.put(
    '/client/watched-history',
    summary = '視聴履歴更新 API',
    response_description = 'サーバー側でマージした最新の視聴履歴。',
    response_model = schemas.WatchedHistory,
)
async def WatchedHistoryUpdateAPI(
    watched_history: Annotated[schemas.WatchedHistory, Body(description='端末上で更新された視聴履歴。')],
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    端末から受信した視聴履歴を、ログイン中ユーザーの履歴へマージする。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されていないとアクセスできない。

    Args:
        watched_history (schemas.WatchedHistory): 端末上で更新された視聴履歴。
        current_user (User): JWT から解決したログイン中のユーザー。

    Returns:
        schemas.WatchedHistory: サーバー側でマージした最新の視聴履歴。
    """

    # Web 側の設定同期と複数端末からの履歴更新を直列化し、JSON カラムの更新競合を防ぐ
    lock = GetClientSettingsUpdateLock(current_user.id)
    async with lock:
        # ロック待ちの間に他のリクエストが client_settings を更新している可能性があるため、最新の値を読み直す
        await current_user.refresh_from_db(fields=['client_settings'])
        client_settings = ClientSettings.model_validate(current_user.client_settings)
        merged_history = MergeWatchedHistory(
            client_settings.watched_history,
            [item.model_dump() for item in watched_history.items],
            client_settings.video_watched_history_max_count,
        )
        updated_settings = dict(client_settings)
        updated_settings['watched_history'] = merged_history
        current_user.client_settings = updated_settings
        await current_user.save()

    # マージ結果も dict のリストなので、スキーマへ明示的に変換して返す
    return schemas.WatchedHistory(
        items = [schemas.WatchedHistoryItem.model_validate(item) for item in merged_history],
    )


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


class _TemplateValidationRequest(BaseModel):
    template: str


@router.post(
    '/notification/validate-template',
    summary = 'Telegram 通知テンプレート検証 API',
    response_description = 'テンプレートの検証結果とプレビューテキスト。',
)
async def ValidateTelegramTemplateAPI(
    request: _TemplateValidationRequest,
    current_user: Annotated[User, Depends(GetCurrentUser)],
) -> dict[str, str]:
    """
    Telegram 通知テンプレートの書式を検証し、サンプルデータでレンダリングしたプレビューテキストを返す。<br>
    テンプレートに未知の変数名や書式エラーが含まれる場合は 422 エラーを返す。<br>
    JWT エンコードされたアクセストークンがリクエストの Authorization: Bearer に設定されていないとアクセスできない。
    """

    template = request.template.strip()
    if not template:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = 'Template is empty.',
        )

    # サンプルデータで {変数名} プレースホルダーを展開し、書式エラーを検出する
    # HTML エスケープは実際の通知送信と同じように適用する
    try:
        preview = template.format_map({
            'title': html_module.escape('サンプル番組タイトル'),
            'channel': html_module.escape('NHK総合'),
            'date': html_module.escape('2025/03/17'),
            'start_time': html_module.escape('21:00'),
            'end_time': html_module.escape('22:00'),
            'duration': '60分',
            'description': html_module.escape('これはサンプルの番組概要です。テンプレートが正しく機能しているか確認できます。'),
            'file_size': html_module.escape('2.34 GB'),
            'warning': '',
        })
    except KeyError as ex:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = f'Unknown variable in template: {ex}. Available variables: {{title}}, {{channel}}, {{date}}, {{start_time}}, {{end_time}}, {{duration}}, {{description}}, {{file_size}}, {{warning}}',
        )
    except ValueError as ex:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = f'Template format error: {ex}. Check for unmatched {{ or }} characters.',
        )

    return {'preview': preview}
