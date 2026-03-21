
# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from app import logging
from app.constants import LIBRARY_PATH
from app.models.EncodingTask import EncodingTask


class EncodingQueueManager:
    """
    バッチエンコードキューを管理するシングルトンクラス。
    Amatsukaze のキューマネージャーに着想を得て、録画 TS ファイルの MP4 へのバッチトランスコードを管理する。
    バックグラウンドで定期的に DB を監視し、Pending タスクを優先度順に取り出して順次エンコードする。

    同時に実行されるエンコードタスクは1つのみ (CPU/GPU リソースの競合を避けるため)。
    エンコーダーの stderr 出力をパースして進捗率を算出し、DB に定期的に反映する。
    """

    # キューのポーリング間隔 (秒)
    POLL_INTERVAL_SECONDS: ClassVar[float] = 5.0

    # 進捗率の DB 更新間隔 (秒)
    PROGRESS_UPDATE_INTERVAL_SECONDS: ClassVar[float] = 1.0

    # シングルトンインスタンス
    _instance: ClassVar[EncodingQueueManager | None] = None

    # 現在実行中のエンコードタスクの ID (なければ None)
    _current_task_id: int | None = None

    # 現在実行中のエンコーダープロセス
    _encoder_process: asyncio.subprocess.Process | None = None

    # バックグラウンドタスクの参照
    _background_task: asyncio.Task[None] | None = None

    # キャンセルが要求されたかどうかのフラグ
    _cancel_requested: bool = False


    def __init__(self) -> None:
        """
        EncodingQueueManager のインスタンスを初期化する。
        直接インスタンス化せず、start() クラスメソッドで起動すること。
        """
        self._current_task_id = None
        self._encoder_process = None
        self._cancel_requested = False


    @classmethod
    def start(cls) -> None:
        """
        EncodingQueueManager をバックグラウンドタスクとして起動する。
        サーバー起動時に app.py から呼び出される。
        """
        if cls._instance is not None:
            logging.warning('[EncodingQueueManager] Already started, skipping.')
            return

        cls._instance = cls()
        cls._background_task = asyncio.create_task(cls._instance._run())
        logging.info('[EncodingQueueManager] Background queue manager started.')


    @classmethod
    def getInstance(cls) -> EncodingQueueManager | None:
        """
        EncodingQueueManager のシングルトンインスタンスを取得する。

        Returns:
            EncodingQueueManager | None: インスタンス (未起動の場合は None)
        """
        return cls._instance


    @classmethod
    async def cancelTask(cls, task_id: int) -> bool:
        """
        指定されたエンコードタスクをキャンセルする。
        タスクが Pending の場合は DB ステータスを Cancelled に更新するだけで済む。
        タスクが Encoding 中の場合はエンコーダープロセスを強制終了する。

        Args:
            task_id (int): キャンセルするタスクの ID

        Returns:
            bool: キャンセルに成功した場合は True
        """
        task = await EncodingTask.get_or_none(id=task_id)
        if task is None:
            return False

        if task.status == 'Pending':
            # Pending タスクは DB ステータスを変更するだけ
            task.status = 'Cancelled'
            await task.save()
            logging.info(f'[EncodingQueueManager] Cancelled pending task. [task_id: {task_id}]')
            return True

        if task.status == 'Encoding':
            # 現在エンコード中のタスクの場合、プロセスを kill する
            instance = cls.getInstance()
            if instance is not None and instance._current_task_id == task_id:
                instance._cancel_requested = True
                if instance._encoder_process is not None:
                    try:
                        instance._encoder_process.kill()
                    except ProcessLookupError:
                        pass
                logging.info(f'[EncodingQueueManager] Cancellation requested for encoding task. [task_id: {task_id}]')
                return True

        return False


    async def _run(self) -> None:
        """
        バックグラウンドで定期的にキューを監視し、Pending タスクを順次エンコードするメインループ。
        """
        logging.info('[EncodingQueueManager] Queue polling loop started.')

        while True:
            try:
                # Pending タスクを優先度降順・追加日時昇順で1件取得
                task = await EncodingTask.filter(status='Pending').order_by('-priority', 'added_at').first()

                if task is not None:
                    # タスクを実行する
                    await self._executeTask(task)

            except Exception:
                logging.error('[EncodingQueueManager] Unexpected error in queue polling loop.', exc_info=True)

            # ポーリング間隔分スリープ
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)


    async def _executeTask(self, task: EncodingTask) -> None:
        """
        1件のエンコードタスクを実行する。
        FFmpeg または HWEncC を使って TS → MP4 のトランスコードを行い、
        エンコーダーの stderr 出力から進捗率をパースして DB に定期的に反映する。

        Args:
            task (EncodingTask): 実行するエンコードタスク
        """

        self._current_task_id = task.id
        self._cancel_requested = False

        # ソースファイルの存在チェック
        source_path = Path(task.source_file_path)
        if not source_path.exists():
            task.status = 'Failed'
            task.fail_reason = f'Source file not found: {task.source_file_path}'
            await task.save()
            logging.error(f'[EncodingQueueManager] Source file not found. [task_id: {task.id}, path: {task.source_file_path}]')
            self._current_task_id = None
            return

        # 出力ファイルパスを決定する (ソースファイルと同じディレクトリに .mp4 拡張子で出力)
        output_path = source_path.with_suffix('.mp4')
        # 出力ファイルが既に存在する場合は連番を付ける
        counter = 1
        while output_path.exists():
            output_path = source_path.with_stem(f'{source_path.stem}_{counter}').with_suffix('.mp4')
            counter += 1
        task.output_file_path = str(output_path)

        # ステータスを Encoding に更新
        task.status = 'Encoding'
        task.progress = 0.0
        task.encoding_started_at = datetime.now()
        await task.save()
        logging.info(f'[EncodingQueueManager] Encoding started. [task_id: {task.id}, source: {task.source_file_path}]')

        try:
            # ソースファイルの長さを取得 (FFprobe で)
            duration = await self._getSourceDuration(task.source_file_path)
            if duration <= 0:
                raise RuntimeError('Failed to determine source file duration.')

            # エンコーダーコマンドを組み立てて実行
            encoder_options = self._buildEncoderCommand(task)
            encoder_type = task.encoder_type

            # エンコーダーのバイナリパスを取得
            encoder_path = LIBRARY_PATH.get(encoder_type if encoder_type != 'FFmpeg' else 'FFmpeg')
            if encoder_path is None or not Path(encoder_path).exists():
                raise RuntimeError(f'Encoder binary not found: {encoder_type}')

            logging.info(f'[EncodingQueueManager] Launching encoder. [task_id: {task.id}, encoder: {encoder_type}]')

            # エンコーダープロセスを起動
            self._encoder_process = await asyncio.subprocess.create_subprocess_exec(
                encoder_path, *encoder_options,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL if encoder_type == 'FFmpeg' else asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # stderr からエンコード進捗をパースしながらプロセスの完了を待つ
            assert self._encoder_process.stderr is not None
            await self._monitorProgress(task, self._encoder_process.stderr, duration)

            # プロセスの終了を待つ
            return_code = await self._encoder_process.wait()

            if self._cancel_requested:
                # キャンセルされた場合
                task.status = 'Cancelled'
                task.encoding_finished_at = datetime.now()
                await task.save()
                # 中途半端な出力ファイルを削除
                if Path(task.output_file_path).exists():
                    Path(task.output_file_path).unlink()
                logging.info(f'[EncodingQueueManager] Encoding cancelled. [task_id: {task.id}]')

            elif return_code == 0:
                # 正常終了
                task.status = 'Completed'
                task.progress = 100.0
                task.encoding_finished_at = datetime.now()
                await task.save()
                logging.info(f'[EncodingQueueManager] Encoding completed. [task_id: {task.id}, output: {task.output_file_path}]')

            else:
                # 異常終了
                task.status = 'Failed'
                task.fail_reason = f'Encoder exited with code {return_code}'
                task.encoding_finished_at = datetime.now()
                await task.save()
                # 中途半端な出力ファイルを削除
                if Path(task.output_file_path).exists():
                    Path(task.output_file_path).unlink()
                logging.error(f'[EncodingQueueManager] Encoding failed. [task_id: {task.id}, return_code: {return_code}]')

        except Exception as ex:
            # 予期しないエラー
            task.status = 'Failed'
            task.fail_reason = str(ex)
            task.encoding_finished_at = datetime.now()
            await task.save()
            # 中途半端な出力ファイルを削除
            if task.output_file_path and Path(task.output_file_path).exists():
                Path(task.output_file_path).unlink()
            logging.error(f'[EncodingQueueManager] Encoding task failed with exception. [task_id: {task.id}]', exc_info=True)

        finally:
            self._encoder_process = None
            self._current_task_id = None
            self._cancel_requested = False


    async def _getSourceDuration(self, file_path: str) -> float:
        """
        FFprobe を使ってソースファイルの長さ (秒) を取得する。

        Args:
            file_path (str): ソースファイルのパス

        Returns:
            float: ファイルの長さ (秒)。取得に失敗した場合は 0.0
        """
        ffprobe_path = LIBRARY_PATH.get('FFprobe')
        if ffprobe_path is None:
            return 0.0

        try:
            process = await asyncio.subprocess.create_subprocess_exec(
                ffprobe_path,
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            duration_str = stdout.decode().strip()
            return float(duration_str)
        except (ValueError, OSError):
            return 0.0


    def _buildEncoderCommand(self, task: EncodingTask) -> list[str]:
        """
        エンコーダーに渡すコマンドラインオプションを組み立てる。
        FFmpeg の場合は TS → MP4 のトランスコードコマンドを、
        HWEncC の場合は同様の変換コマンドを返す。

        Args:
            task (EncodingTask): エンコードタスク

        Returns:
            list[str]: エンコーダーに渡すオプションの配列
        """

        if task.encoder_type == 'FFmpeg':
            return self._buildFFmpegCommand(task)
        else:
            return self._buildHWEncCCommand(task)


    def _buildFFmpegCommand(self, task: EncodingTask) -> list[str]:
        """
        FFmpeg 用のコマンドラインオプションを組み立てる (TS → MP4 バッチトランスコード)。

        Args:
            task (EncodingTask): エンコードタスク

        Returns:
            list[str]: FFmpeg に渡すオプションの配列
        """

        options: list[str] = []

        # 入力ファイル
        options.extend(['-i', task.source_file_path])

        # ストリームマッピング: 映像1ストリーム + 音声1ストリーム
        options.extend(['-map', '0:v:0', '-map', '0:a:0'])

        # 映像コーデック
        if task.video_codec == 'H.265':
            options.extend(['-vcodec', 'libx265'])
            options.extend(['-profile:v', 'main'])
        else:
            options.extend(['-vcodec', 'libx264'])
            options.extend(['-profile:v', 'high'])

        # 映像ビットレートとプリセット
        options.extend(['-b:v', task.video_bitrate])
        options.extend(['-preset', task.quality_preset])

        # インターレース解除 (yadif フィルタ)
        options.extend(['-vf', 'yadif=mode=0:parity=-1:deint=1'])

        # ピクセルフォーマット
        options.extend(['-pix_fmt', 'yuv420p'])

        # 音声コーデック
        options.extend(['-acodec', 'aac', '-ac', '2', '-ab', task.audio_bitrate, '-ar', '48000'])

        # 出力形式: MP4
        options.extend(['-movflags', '+faststart'])
        options.extend(['-y', task.output_file_path])

        return options


    def _buildHWEncCCommand(self, task: EncodingTask) -> list[str]:
        """
        HWEncC (QSVEncC/NVEncC/VCEEncC/rkmppenc) 用のコマンドラインオプションを組み立てる。

        Args:
            task (EncodingTask): エンコードタスク

        Returns:
            list[str]: HWEncC に渡すオプションの配列
        """

        options: list[str] = []

        # 入力
        options.extend(['--input-format', 'mpegts', '-i', task.source_file_path])

        # VCEEncC は HW デコーダーが TS で不安定なため SW デコーダーを利用
        if task.encoder_type == 'VCEEncC':
            options.append('--avsw')
        else:
            options.append('--avhw')

        # 映像コーデック
        if task.video_codec == 'H.265':
            options.extend(['--codec', 'hevc'])
        else:
            options.extend(['--codec', 'h264'])

        # ビットレート
        options.extend(['--vbr', task.video_bitrate.replace('k', '')])

        # 音声設定: ステレオにダウンミックス
        options.extend(['--audio-codec', 'aac', '--audio-stream', 'stereo', '--audio-bitrate', task.audio_bitrate.replace('k', '')])

        # インターレース解除
        options.extend(['--interlace', 'tff', '--vpp-deinterlace', 'normal'])

        # 出力: MP4 形式
        options.extend(['--output-format', 'mp4', '-o', task.output_file_path])

        return options


    async def _monitorProgress(
        self,
        task: EncodingTask,
        stderr_stream: asyncio.StreamReader,
        duration: float,
    ) -> None:
        """
        エンコーダーの stderr 出力を監視し、進捗率をパースして DB に定期的に反映する。
        FFmpeg は stderr に 'time=HH:MM:SS.SS' 形式で現在の処理位置を出力する。
        HWEncC は stderr に進捗率 (%) を直接出力する。

        Args:
            task (EncodingTask): エンコードタスク
            stderr_stream (asyncio.StreamReader): エンコーダーの stderr ストリーム
            duration (float): ソースファイルの長さ (秒)
        """

        last_update_time = time.time()

        # FFmpeg の time= パターン (例: time=01:23:45.67)
        ffmpeg_time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})')
        # HWEncC の進捗率パターン (例: [53.2%])
        hwencc_progress_pattern = re.compile(r'\[(\d+\.?\d*)%\]')

        while True:
            # stderr から1行分のデータを読み取る (最大 4096 バイト)
            try:
                data = await asyncio.wait_for(stderr_stream.read(4096), timeout=60.0)
            except TimeoutError:
                # タイムアウトしたがプロセスが終了していない場合は続行
                if self._encoder_process is not None and self._encoder_process.returncode is None:
                    continue
                break

            if not data:
                break

            line = data.decode('utf-8', errors='replace')

            # 進捗率をパース
            progress = None
            if task.encoder_type == 'FFmpeg':
                # FFmpeg: time=HH:MM:SS.SS から現在の処理位置を算出
                match = ffmpeg_time_pattern.search(line)
                if match:
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    seconds = int(match.group(3))
                    centiseconds = int(match.group(4))
                    current_time = hours * 3600 + minutes * 60 + seconds + centiseconds / 100.0
                    progress = min((current_time / duration) * 100.0, 99.9)
            else:
                # HWEncC: [XX.X%] 形式の進捗率を直接取得
                match = hwencc_progress_pattern.search(line)
                if match:
                    progress = min(float(match.group(1)), 99.9)

            # 進捗率を DB に更新 (更新間隔を制限して DB 負荷を軽減)
            if progress is not None:
                now = time.time()
                if now - last_update_time >= self.PROGRESS_UPDATE_INTERVAL_SECONDS:
                    task.progress = round(progress, 1)
                    await task.save(update_fields=['progress', 'updated_at'])
                    last_update_time = now
