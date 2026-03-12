
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import ClassVar

import aiohttp

from app import logging
from app.config import Config
from app.constants import API_REQUEST_HEADERS, JST
from app.models.MirakurunReservation import MirakurunReservation
from app.utils import GetMirakurunAPIEndpointURL


# ストリームの読み取りチャンクサイズ (64 KB)
_CHUNK_SIZE = 65536

# 録画開始を試みる時間的猶予 (秒): 開始時刻のこの秒数前から録画準備を開始する
_START_LOOKAHEAD_SECONDS = 60

# 録画開始タイムアウト (秒): Mirakurun に接続しても最初のデータが届くまでの最大待機時間
_STREAM_START_TIMEOUT = 20

# ファイル名として使えない文字のパターン (Windows / Linux 共通)
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _sanitizeFilename(name: str) -> str:
    """
    ファイル名に使えない文字を全角相当の文字または空白に置換する。

    Args:
        name (str): 元のファイル名文字列

    Returns:
        str: サニタイズ済みファイル名文字列
    """
    # 制御文字・記号類を '_' に置換
    sanitized = _UNSAFE_FILENAME_RE.sub('_', name)
    # 連続する空白・アンダースコアをまとめる
    sanitized = re.sub(r'[_\s]+', '_', sanitized).strip('_')
    return sanitized or 'untitled'


class MirakurunRecordingTask:
    """
    Mirakurun バックエンドで録画予約を管理する常駐タスク。

    EPGStation の RecordingManageModel / RecorderModel に相当するロジックを提供する。
    定期的にデータベースを参照し、録画開始時刻が近づいた MirakurunReservation を検出して
    aiohttp 経由で Mirakurun の Service Stream API からストリームを取得し、
    設定された録画フォルダに MPEG2-TS ファイルとして保存する。

    並行録画に対応しており、各録画は独立した asyncio.Task として管理される。
    """

    # クラス変数: 実行中の録画 Task を reservation_id -> asyncio.Task で管理
    _recording_tasks: ClassVar[dict[int, asyncio.Task[None]]] = {}

    def __init__(self) -> None:
        """
        コンストラクタ。
        - _scheduler_task: スケジューラーループの asyncio.Task
        """
        # スケジューラーループを保持する Task (None のときは停止中)
        self._scheduler_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """
        スケジューラーを開始する。
        既に開始済みの場合は何もしない。
        """
        if self._scheduler_task is not None and not self._scheduler_task.done():
            return
        self._scheduler_task = asyncio.create_task(self._schedulerLoop(), name='MirakurunRecordingScheduler')
        logging.info('MirakurunRecordingTask: Scheduler started.')

    async def stop(self) -> None:
        """
        スケジューラーと全ての進行中録画タスクを停止する。
        サーバーシャットダウン時に呼び出される。
        """
        # スケジューラーを停止
        if self._scheduler_task is not None and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None

        # 進行中の全録画タスクをキャンセル
        for reservation_id, task in list(MirakurunRecordingTask._recording_tasks.items()):
            if not task.done():
                logging.info(f'MirakurunRecordingTask: Cancelling recording task for reservation_id={reservation_id}.')
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        MirakurunRecordingTask._recording_tasks.clear()

        logging.info('MirakurunRecordingTask: Scheduler stopped.')

    async def _schedulerLoop(self) -> None:
        """
        スケジューラーのメインループ。
        30 秒ごとに Pending な予約を確認し、開始時刻が近いものの録画を開始する。
        """
        while True:
            try:
                await self._checkAndStartRecordings()
            except Exception:
                logging.error('MirakurunRecordingTask: Unexpected error in scheduler loop.', exc_info=True)
            # 30 秒待機してから再チェック
            await asyncio.sleep(30)

    async def _checkAndStartRecordings(self) -> None:
        """
        録画開始時刻が _START_LOOKAHEAD_SECONDS 秒以内の Pending 予約を取得し、
        まだ録画タスクが起動していないものについて録画タスクを生成する。
        """
        now = datetime.now(tz=JST)
        # 有効開始時刻 = start_time - start_margin であるが、DB には start_time のみ保存されているため
        # 余裕を見て _START_LOOKAHEAD_SECONDS 秒以内に start_time が来る予約をまとめて取得する
        lookahead_cutoff = now + timedelta(seconds=_START_LOOKAHEAD_SECONDS)

        # Pending 且つ start_time が lookahead_cutoff 以内の予約を取得
        upcoming: list[MirakurunReservation] = await MirakurunReservation.filter(
            status='Pending',
            start_time__lte=lookahead_cutoff,
        ).all()

        for reservation in upcoming:
            # 既に録画タスクが起動済みの場合はスキップ
            if reservation.id in MirakurunRecordingTask._recording_tasks:
                existing_task = MirakurunRecordingTask._recording_tasks[reservation.id]
                if not existing_task.done():
                    continue
                # タスクが終了済みなら辞書から除去して再チェック可能にする
                del MirakurunRecordingTask._recording_tasks[reservation.id]

            # 録画タスクを生成して辞書に登録
            task = asyncio.create_task(
                self._recordStream(reservation.id),
                name=f'MirakurunRecording-{reservation.id}',
            )
            MirakurunRecordingTask._recording_tasks[reservation.id] = task
            logging.info(
                f'MirakurunRecordingTask: Scheduled recording task for reservation_id={reservation.id} '
                f'(title="{reservation.title}", start_time={reservation.start_time.isoformat()}).'
            )

    async def _recordStream(self, reservation_id: int) -> None:
        """
        1 件の録画予約に対して Mirakurun からストリームを取得してファイルに書き込む。

        Args:
            reservation_id (int): 録画対象の MirakurunReservation の主キー
        """
        # 予約を DB から再取得 (最新状態を反映)
        reservation = await MirakurunReservation.get_or_none(id=reservation_id)
        if reservation is None:
            logging.warning(f'MirakurunRecordingTask: reservation_id={reservation_id} not found, aborting.')
            return

        # キャンセル済み予約は録画しない
        if reservation.status == 'Cancelled':
            logging.info(f'MirakurunRecordingTask: reservation_id={reservation_id} is cancelled, skipping.')
            return

        # 有効開始時刻まで待機する
        effective_start = reservation.getEffectiveStartTime()
        now = datetime.now(tz=JST)
        wait_seconds = (effective_start - now).total_seconds()
        if wait_seconds > 0:
            logging.info(
                f'MirakurunRecordingTask: Waiting {wait_seconds:.1f}s before recording '
                f'reservation_id={reservation_id} ("{reservation.title}").'
            )
            await asyncio.sleep(wait_seconds)

        # 再度 DB から取得して最新状態を確認 (待機中にキャンセルされた可能性がある)
        reservation = await MirakurunReservation.get_or_none(id=reservation_id)
        if reservation is None or reservation.status == 'Cancelled':
            logging.info(f'MirakurunRecordingTask: reservation_id={reservation_id} cancelled during wait, aborting.')
            return

        # 録画先フォルダを決定する
        # RecordSettings に recording_folders が指定されていればそれを優先し、
        # なければ Config().video.recorded_folders の先頭を使う
        record_settings = reservation.getRecordSettings()
        output_dir: Path | None = None
        if record_settings.recording_folders:
            output_dir = Path(record_settings.recording_folders[0].recording_folder_path)
        else:
            config_folders = Config().video.recorded_folders
            if config_folders:
                output_dir = config_folders[0]

        if output_dir is None:
            logging.error(
                f'MirakurunRecordingTask: No recording folder configured for reservation_id={reservation_id}. '
                'Set video.recorded_folders in config.yaml.'
            )
            reservation.status = 'Failed'  # type: ignore[assignment]
            await reservation.save()
            return

        # ファイル名を構築: {title}_{YYYYMMDD_HHMMSS}_{channel_name}.m2ts
        safe_title = _sanitizeFilename(reservation.title)
        start_str = reservation.start_time.astimezone(JST).strftime('%Y%m%d_%H%M%S')
        channel_name = ''
        if reservation.channel_id:
            from app.models.Channel import Channel
            channel = await Channel.get_or_none(id=reservation.channel_id)
            if channel:
                channel_name = '_' + _sanitizeFilename(channel.name)
        file_name = f'{safe_title}_{start_str}{channel_name}.m2ts'
        output_path = output_dir / file_name

        # 同名ファイルが既に存在する場合は連番サフィックスを付与する
        counter = 1
        while output_path.exists():
            output_path = output_dir / f'{safe_title}_{start_str}{channel_name}_{counter}.m2ts'
            counter += 1

        # Mirakurun 形式のサービス ID を計算
        mirakurun_service_id = reservation.getMirakurunServiceId()
        stream_url = GetMirakurunAPIEndpointURL(f'/api/services/{mirakurun_service_id}/stream')

        # ステータスを Recording に更新
        reservation.status = 'Recording'  # type: ignore[assignment]
        reservation.recording_file_path = str(output_path)
        await reservation.save()
        logging.info(
            f'MirakurunRecordingTask: Starting recording reservation_id={reservation_id} '
            f'-> "{output_path}" (service_id={mirakurun_service_id}).'
        )

        # Mirakurun の Service Stream API に接続してストリームをファイルへ書き込む
        effective_end = reservation.getEffectiveEndTime()
        session: aiohttp.ClientSession | None = None
        try:
            # X-Mirakurun-Priority: 指定した録画設定の優先度をそのまま渡す (EPGStation の recPriority に相当)
            priority_header = str(record_settings.priority)
            session = aiohttp.ClientSession()
            response = await session.get(
                url=stream_url,
                headers={**API_REQUEST_HEADERS, 'X-Mirakurun-Priority': priority_header},
                timeout=aiohttp.ClientTimeout(connect=_STREAM_START_TIMEOUT, sock_connect=_STREAM_START_TIMEOUT, sock_read=None),
            )

            if response.status != 200:
                logging.error(
                    f'MirakurunRecordingTask: Mirakurun returned HTTP {response.status} for '
                    f'reservation_id={reservation_id} (url={stream_url}).'
                )
                reservation.status = 'Failed'  # type: ignore[assignment]
                await reservation.save()
                return

            # 出力先ディレクトリが存在しない場合は作成する
            output_dir.mkdir(parents=True, exist_ok=True)

            # ストリームをファイルへ書き込む
            # effective_end になったら asyncio.wait_for でタイムアウトさせる
            bytes_written = 0
            with open(output_path, 'wb') as f:
                while True:
                    # 残り録画時間を計算して次のチャンクの読み取りタイムアウトを設定
                    remaining = (effective_end - datetime.now(tz=JST)).total_seconds()
                    if remaining <= 0:
                        # 録画終了時刻に到達
                        break
                    try:
                        chunk = await asyncio.wait_for(
                            response.content.read(_CHUNK_SIZE),
                            timeout=min(remaining + 5, 30),  # 残り時間 + 5 秒の余裕
                        )
                    except TimeoutError:
                        # タイムアウト = 録画終了時刻超過または受信停止
                        logging.info(
                            f'MirakurunRecordingTask: Stream read timed out for reservation_id={reservation_id}, '
                            'ending recording.'
                        )
                        break
                    if not chunk:
                        # ストリームが正常に終端に達した
                        logging.info(
                            f'MirakurunRecordingTask: Stream ended for reservation_id={reservation_id}.'
                        )
                        break
                    f.write(chunk)
                    bytes_written += len(chunk)

            logging.info(
                f'MirakurunRecordingTask: Recording completed for reservation_id={reservation_id}. '
                f'Written {bytes_written / 1024 / 1024:.1f} MB to "{output_path}".'
            )

            # ステータスを Completed に更新
            reservation.status = 'Completed'  # type: ignore[assignment]
            await reservation.save()

        except asyncio.CancelledError:
            # シャットダウンなどによるキャンセル: ファイルが途中まで書き込まれている場合はそのまま残す
            logging.warning(
                f'MirakurunRecordingTask: Recording cancelled for reservation_id={reservation_id}. '
                'Partial file may exist.'
            )
            reservation.status = 'Failed'  # type: ignore[assignment]
            await reservation.save()
            raise  # CancelledError は再送出して asyncio に伝える

        except (aiohttp.ClientConnectorError, aiohttp.ClientError, TimeoutError) as e:
            logging.error(
                f'MirakurunRecordingTask: Network error during recording reservation_id={reservation_id}: {e}'
            )
            reservation.status = 'Failed'  # type: ignore[assignment]
            await reservation.save()

        except Exception:
            logging.error(
                f'MirakurunRecordingTask: Unexpected error during recording reservation_id={reservation_id}.',
                exc_info=True,
            )
            reservation.status = 'Failed'  # type: ignore[assignment]
            await reservation.save()

        finally:
            # aiohttp セッションを確実に閉じる
            if session is not None:
                await session.close()
            # 録画タスク辞書から除去
            MirakurunRecordingTask._recording_tasks.pop(reservation_id, None)

    @classmethod
    def isRecording(cls, reservation_id: int) -> bool:
        """
        指定された予約 ID の録画タスクが実行中かどうかを確認する。

        Args:
            reservation_id (int): チェック対象の予約 ID

        Returns:
            bool: 録画タスクが実行中なら True
        """
        task = cls._recording_tasks.get(reservation_id)
        return task is not None and not task.done()

    @classmethod
    async def cancelRecording(cls, reservation_id: int) -> None:
        """
        実行中の録画タスクをキャンセルする。

        Args:
            reservation_id (int): キャンセル対象の予約 ID
        """
        task = cls._recording_tasks.get(reservation_id)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        cls._recording_tasks.pop(reservation_id, None)
