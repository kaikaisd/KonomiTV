
import html
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from app import logging
from app.constants import THUMBNAILS_DIR


# 日本標準時
JST = ZoneInfo('Asia/Tokyo')

# Telegram Bot API のベース URL
TELEGRAM_API_BASE = 'https://api.telegram.org'

# 通知メッセージに含める番組概要の最大文字数 (これを超えたら末尾を「…」で切る)
DESCRIPTION_MAX_LENGTH = 500

# カスタムテンプレートのデフォルト値 (フロントエンドのプレースホルダーとして表示する)
# {変数名} 形式のプレースホルダーを使用する。変数値は HTML エスケープされた上で HTML モードで送信される
DEFAULT_NOTIFICATION_TEMPLATE = (
    '📺 <b>{title}</b>\n'
    '📡 {channel}  |  🕐 {start_time}〜{end_time} ({duration}分)\n'
    '📝 {description}\n'
    '💾 録画サイズ: {file_size}'
)


class TelegramNotifier:
    """
    Telegram Bot API を使って録画完了通知を送信するユーティリティクラス。
    HTTPx を使った非同期実装で、呼び出し側のイベントループをブロックしない。
    送信に失敗してもログに記録するだけで例外を送出しないため、録画フローには影響しない。
    """

    @staticmethod
    def _escapeMarkdownV2(text: str) -> str:
        """
        Telegram MarkdownV2 エスケープが必要な特殊文字をエスケープする。
        ref: https://core.telegram.org/bots/api#markdownv2-style

        Args:
            text (str): エスケープ対象の文字列

        Returns:
            str: エスケープ済みの文字列
        """
        # MarkdownV2 でエスケープが必要な文字の一覧
        special_chars = r'\_*[]()~`>#+-=|{}.!'
        for ch in special_chars:
            text = text.replace(ch, f'\\{ch}')
        return text

    @staticmethod
    def _formatFileSize(size_bytes: int) -> str:
        """
        ファイルサイズを人間が読みやすい形式 (GB / MB) に変換する。

        Args:
            size_bytes (int): バイト単位のファイルサイズ

        Returns:
            str: フォーマット済みのサイズ文字列 (例: "1.23 GB", "456.7 MB")
        """
        if size_bytes >= 1024 ** 3:
            return f'{size_bytes / 1024 ** 3:.2f} GB'
        return f'{size_bytes / 1024 ** 2:.1f} MB'

    @staticmethod
    def _buildCaption(
        title: str,
        channel_name: str | None,
        start_time_str: str,
        end_time_str: str,
        duration_min: int,
        description: str,
        file_size: int,
    ) -> str:
        """
        通知メッセージの本文 (MarkdownV2 形式) を組み立てる。

        Args:
            title (str): 番組タイトル
            channel_name (str | None): チャンネル名 (不明な場合は None)
            start_time_str (str): 放送開始時刻の文字列 (例: "10:00")
            end_time_str (str): 放送終了時刻の文字列 (例: "11:00")
            duration_min (int): 放送時間 (分)
            description (str): 番組概要
            file_size (int): 録画ファイルサイズ (バイト)

        Returns:
            str: MarkdownV2 形式の通知本文
        """
        # 各テキストをエスケープ
        escaped_title = TelegramNotifier._escapeMarkdownV2(title)
        escaped_channel = TelegramNotifier._escapeMarkdownV2(channel_name or '不明')
        escaped_start = TelegramNotifier._escapeMarkdownV2(start_time_str)
        escaped_end = TelegramNotifier._escapeMarkdownV2(end_time_str)
        escaped_duration = TelegramNotifier._escapeMarkdownV2(str(duration_min))

        # 番組概要を最大文字数で切り詰める
        if len(description) > DESCRIPTION_MAX_LENGTH:
            description = description[:DESCRIPTION_MAX_LENGTH] + '…'
        escaped_description = TelegramNotifier._escapeMarkdownV2(description)

        # ファイルサイズをフォーマット
        escaped_size = TelegramNotifier._escapeMarkdownV2(TelegramNotifier._formatFileSize(file_size))

        lines = [
            f'📺 *{escaped_title}*',
            f'📡 {escaped_channel}  \\|  🕐 {escaped_start}〜{escaped_end} \\({escaped_duration}分\\)',
        ]
        if escaped_description:
            lines.append(f'📝 {escaped_description}')
        lines.append(f'💾 録画サイズ: {escaped_size}')

        return '\n'.join(lines)

    @staticmethod
    def _buildCaptionFromTemplate(
        template: str,
        title: str,
        channel_name: str | None,
        date_str: str,
        start_time_str: str,
        end_time_str: str,
        duration_min: int,
        description: str,
        file_size: int,
    ) -> tuple[str, str]:
        """
        カスタムテンプレートから通知本文 (HTML モード) を組み立てる。
        各変数値は html.escape() で HTML エスケープされた上でテンプレートへ埋め込まれる。
        テンプレートの静的部分には <b>, <i>, <a> などの HTML タグを使用できる。

        使用可能な変数:
            {title}       - 番組タイトル
            {channel}     - チャンネル名
            {date}        - 放送日付 (YYYY/MM/DD)
            {start_time}  - 放送開始時刻 (HH:MM)
            {end_time}    - 放送終了時刻 (HH:MM)
            {duration}    - 放送時間 (単位「分」を含む, 例: "60分")
            {description} - 番組概要
            {file_size}   - 録画ファイルサイズ (例: "1.23 GB")

        Args:
            template (str): カスタムテンプレート文字列
            title (str): 番組タイトル
            channel_name (str | None): チャンネル名 (不明な場合は None)
            date_str (str): 放送日付の文字列 (例: "2025/03/17")
            start_time_str (str): 放送開始時刻の文字列
            end_time_str (str): 放送終了時刻の文字列
            duration_min (int): 放送時間 (分)
            description (str): 番組概要
            file_size (int): 録画ファイルサイズ (バイト)

        Returns:
            tuple[str, str]: (テキスト, parse_mode) のタプル。parse_mode は "HTML"
        """

        # 番組概要を最大文字数で切り詰める
        if len(description) > DESCRIPTION_MAX_LENGTH:
            description = description[:DESCRIPTION_MAX_LENGTH] + '…'

        # 各変数値を HTML エスケープしてからテンプレートへ埋め込む
        # これにより、タイトルや概要に含まれる <>&" などが Telegram HTML モードで誤解釈されるのを防ぐ
        try:
            text = template.format_map({
                'title': html.escape(title),
                'channel': html.escape(channel_name or '不明'),
                'date': html.escape(date_str),
                'start_time': html.escape(start_time_str),
                'end_time': html.escape(end_time_str),
                'duration': f'{duration_min}分',
                'description': html.escape(description),
                'file_size': html.escape(TelegramNotifier._formatFileSize(file_size)),
            })
        except (KeyError, ValueError) as ex:
            # テンプレートの書式が不正な場合はそのまま送信してエラーを記録する
            logging.warning(f'TelegramNotifier: Custom template format error: {ex}. Sending template as-is.')
            text = template

        return text, 'HTML'

    @staticmethod
    async def sendRecordingNotification(
        bot_token: str,
        chat_id: str,
        title: str,
        channel_name: str | None,
        date_jst: str,
        start_time_jst: str,
        end_time_jst: str,
        duration_min: int,
        description: str,
        file_size: int,
        file_hash: str,
        recorded_program_id: int,
        base_url: str,
        notification_template: str = '',
    ) -> bool:
        """
        録画完了通知を Telegram に送信する。
        サムネイルが存在する場合は sendPhoto、なければ sendMessage にフォールバックする。
        インラインキーボードの再生ボタンは base_url が指定されている場合のみ追加する。

        Args:
            bot_token (str): Telegram Bot トークン
            chat_id (str): 送信先のチャット ID またはチャンネル名
            title (str): 番組タイトル
            channel_name (str | None): チャンネル名
            date_jst (str): 放送日付 (YYYY/MM/DD 形式)
            start_time_jst (str): 放送開始時刻 (HH:MM 形式)
            end_time_jst (str): 放送終了時刻 (HH:MM 形式)
            duration_min (int): 放送時間 (分)
            description (str): 番組概要
            file_size (int): 録画ファイルサイズ (バイト)
            file_hash (str): 録画ファイルのハッシュ値 (サムネイルファイル名の特定に使用)
            recorded_program_id (int): 録画番組 ID (再生 URL の生成に使用)
            base_url (str): KonomiTV の公開ベース URL (空文字列の場合は再生ボタンを省略)
            notification_template (str): カスタム通知テンプレート (空文字列の場合はデフォルトの MarkdownV2 形式を使用)

        Returns:
            bool: 送信に成功した場合は True、失敗した場合は False
        """

        # 通知本文と parse_mode を組み立てる
        # カスタムテンプレートが設定されている場合は HTML モードで送信し、未設定の場合はデフォルトの MarkdownV2 形式を使用する
        if notification_template:
            caption, parse_mode = TelegramNotifier._buildCaptionFromTemplate(
                template = notification_template,
                title = title,
                channel_name = channel_name,
                date_str = date_jst,
                start_time_str = start_time_jst,
                end_time_str = end_time_jst,
                duration_min = duration_min,
                description = description,
                file_size = file_size,
            )
        else:
            caption = TelegramNotifier._buildCaption(
                title = title,
                channel_name = channel_name,
                start_time_str = start_time_jst,
                end_time_str = end_time_jst,
                duration_min = duration_min,
                description = description,
                file_size = file_size,
            )
            parse_mode = 'MarkdownV2'

        # インラインキーボード (再生ボタン) を組み立てる
        # base_url が空文字列の場合はボタンを省略する
        reply_markup: dict[str, object] | None = None
        if base_url:
            playback_url = f'{base_url.rstrip("/")}/videos/watch/{recorded_program_id}'
            reply_markup = {
                'inline_keyboard': [[
                    {'text': '▶ 再生 / Watch', 'url': playback_url},
                ]],
            }

        # サムネイルファイルのパスを確認する
        # ファイル名は "{file_hash}.webp" (代表サムネイル) の形式
        thumbnail_path = Path(str(THUMBNAILS_DIR)) / f'{file_hash}.webp'
        has_thumbnail = thumbnail_path.exists()

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if has_thumbnail:
                    # サムネイルが存在する場合は sendPhoto で送信する
                    with open(thumbnail_path, 'rb') as f:
                        thumbnail_bytes = f.read()

                    data: dict[str, object] = {
                        'chat_id': chat_id,
                        'caption': caption,
                        'parse_mode': parse_mode,
                    }
                    if reply_markup is not None:
                        data['reply_markup'] = json.dumps(reply_markup)

                    response = await client.post(
                        url = f'{TELEGRAM_API_BASE}/bot{bot_token}/sendPhoto',
                        data = data,
                        files = {'photo': ('thumbnail.webp', thumbnail_bytes, 'image/webp')},
                    )
                else:
                    # サムネイルがない場合は sendMessage にフォールバックする
                    payload: dict[str, object] = {
                        'chat_id': chat_id,
                        'text': caption,
                        'parse_mode': parse_mode,
                    }
                    if reply_markup is not None:
                        payload['reply_markup'] = reply_markup

                    response = await client.post(
                        url = f'{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage',
                        json = payload,
                    )

                if not response.is_success:
                    logging.error(
                        f'TelegramNotifier: Failed to send recording notification. '
                        f'status={response.status_code} body={response.text}'
                    )
                    return False

                logging.info(
                    f'TelegramNotifier: Sent recording notification for program_id={recorded_program_id} '
                    f'title="{title}"'
                )
                return True

        except Exception:
            logging.error('TelegramNotifier: Unexpected error while sending recording notification.', exc_info=True)
            return False

    @staticmethod
    async def sendTestNotification(
        bot_token: str,
        chat_id: str,
    ) -> bool:
        """
        Telegram 通知設定が正しく機能するか確認するためのテスト通知を送信する。
        sendMessage を使ってシンプルなテキストメッセージを送る。

        Args:
            bot_token (str): Telegram Bot トークン
            chat_id (str): 送信先のチャット ID またはチャンネル名

        Returns:
            bool: 送信に成功した場合は True、失敗した場合は False
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    url = f'{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage',
                    json = {
                        'chat_id': chat_id,
                        'text': '✅ KonomiTV の Telegram 通知設定が正常に動作しています。',
                    },
                )
                if not response.is_success:
                    logging.error(
                        f'TelegramNotifier: Test notification failed. '
                        f'status={response.status_code} body={response.text}'
                    )
                    return False
                return True
        except Exception:
            logging.error('TelegramNotifier: Unexpected error while sending test notification.', exc_info=True)
            return False
