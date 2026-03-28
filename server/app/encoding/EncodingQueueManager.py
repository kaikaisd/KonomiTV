
# Type Hints を指定できるように
# ref: https://stackoverflow.com/a/33533514/17124142
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from app import logging, schemas
from app.config import Config
from app.constants import LIBRARY_PATH
from app.models.EncodingTask import EncodingTask
from app.models.RecordedVideo import RecordedVideo


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

        # 出力ファイルパスを決定する
        # サーバー設定で出力ディレクトリが指定されている場合はそこに出力し、
        # 指定されていない場合はソースファイルと同じディレクトリに出力する
        # 拡張子は出力コンテナ形式に応じて決定する
        output_ext_map = {'MP4': '.mp4', 'MKV': '.mkv', 'WebM': '.webm'}
        output_ext = output_ext_map.get(task.output_format, '.mp4')
        encoding_config = Config().encoding
        if encoding_config.output_directory and Path(encoding_config.output_directory).is_dir():
            output_dir = Path(encoding_config.output_directory)
            output_path = output_dir / f'{source_path.stem}{output_ext}'
        else:
            output_path = source_path.with_suffix(output_ext)
        # 出力ファイルが既に存在する場合は連番を付ける
        base_stem = output_path.stem
        output_dir_for_counter = output_path.parent
        counter = 1
        while output_path.exists():
            output_path = output_dir_for_counter / f'{base_stem}_{counter}{output_ext}'
            counter += 1
        task.output_file_path = str(output_path)

        # CM 分離出力時の CM ファイルパスを決定する
        if task.cm_processing == 'SeparateOutput':
            cm_path = output_path.parent / f'{output_path.stem}_CM{output_ext}'
            cm_counter = 1
            while cm_path.exists():
                cm_path = output_path.parent / f'{output_path.stem}_CM_{cm_counter}{output_ext}'
                cm_counter += 1
            task.cm_output_file_path = str(cm_path)

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

            # CM 区間情報を取得 (CM 処理が有効な場合)
            cm_sections = await self._getCMSections(task)
            keep_segments: list[tuple[float, float]] | None = None
            if cm_sections is not None:
                keep_segments = self._computeKeepSegments(cm_sections, duration)
                if len(keep_segments) == 0:
                    raise RuntimeError('No content segments remain after CM removal.')
                logging.info(f'[EncodingQueueManager] CM processing enabled. '
                             f'[task_id: {task.id}, mode: {task.cm_processing}, '
                             f'cm_sections: {len(cm_sections)}, keep_segments: {len(keep_segments)}]')

            # HWEncC の CM 除去に必要なソース映像のフレームレートを RecordedVideo から取得する
            # HWEncC の --trim オプションはフレーム番号で指定するため、秒からフレーム番号への変換に使う
            source_frame_rate: float | None = None
            if keep_segments is not None and task.encoder_type != 'FFmpeg' and task.recorded_video_id is not None:
                recorded_video = await RecordedVideo.get_or_none(id=task.recorded_video_id)
                if recorded_video is not None:
                    source_frame_rate = recorded_video.video_frame_rate

            # === パス1: 本編のエンコード ===
            # CM 除去が有効な場合は keep_segments (本編区間) のみをエンコードする
            encoder_options = self._buildEncoderCommand(task, keep_segments, source_frame_rate)
            encoder_type = task.encoder_type

            # エンコーダーのバイナリパスを取得
            encoder_path = LIBRARY_PATH.get(encoder_type if encoder_type != 'FFmpeg' else 'FFmpeg')
            if encoder_path is None or not Path(encoder_path).exists():
                raise RuntimeError(f'Encoder binary not found: {encoder_type}')

            logging.info(f'[EncodingQueueManager] Launching encoder (main content). [task_id: {task.id}, encoder: {encoder_type}]')

            # CM 除去時は本編区間の合計時間をエンコード対象の実効時間として使う
            # FFmpeg の time= 出力はデコード後の出力タイムラインを示すため、
            # trim/concat で切り出した本編のみの場合は実効時間で割らないと進捗率が正しくならない
            # HWEncC は進捗率を直接出力するため影響なし
            effective_duration = duration
            if keep_segments is not None:
                effective_duration = sum(end - start for start, end in keep_segments)

            # エンコーダープロセスを起動
            return_code = await self._runEncoder(task, encoder_path, encoder_options, effective_duration)

            # キャンセルチェック
            if self._cancel_requested:
                task.status = 'Cancelled'
                task.encoding_finished_at = datetime.now()
                await task.save()
                self._cleanupOutputFiles(task)
                logging.info(f'[EncodingQueueManager] Encoding cancelled. [task_id: {task.id}]')

            elif return_code != 0:
                task.status = 'Failed'
                task.fail_reason = f'Encoder exited with code {return_code}'
                task.encoding_finished_at = datetime.now()
                await task.save()
                self._cleanupOutputFiles(task)
                logging.error(f'[EncodingQueueManager] Encoding failed. [task_id: {task.id}, return_code: {return_code}]')

            else:
                # === パス1 正常終了 ===
                logging.info(f'[EncodingQueueManager] Main content encoding completed. '
                             f'[task_id: {task.id}, output: {task.output_file_path}]')

                # === パス2: SeparateOutput モードの場合、CM 区間を別ファイルにエンコードする ===
                # Amatsukaze の CM 分離出力に相当する機能: 本編とは別に CM 区間のみを結合して出力する
                # cm_video_bitrate が指定されている場合は CM ファイルに異なるビットレートを適用する
                if task.cm_processing == 'SeparateOutput' and cm_sections is not None and task.cm_output_file_path:
                    cm_segments = [(cm['start_time'], cm['end_time']) for cm in cm_sections]
                    if len(cm_segments) > 0:
                        logging.info(f'[EncodingQueueManager] Launching encoder (CM segments). '
                                     f'[task_id: {task.id}, cm_segments: {len(cm_segments)}]')

                        # CM 用のビットレートを決定する (空文字列の場合は本編と同じビットレートを使用)
                        cm_video_bitrate = task.cm_video_bitrate if task.cm_video_bitrate else task.video_bitrate

                        # CM 区間用のエンコーダーコマンドを組み立てる
                        cm_encoder_options = self._buildEncoderCommand(
                            task, cm_segments, source_frame_rate,
                            output_path_override=task.cm_output_file_path,
                            video_bitrate_override=cm_video_bitrate,
                        )

                        # CM 区間の実効時間
                        cm_effective_duration = sum(end - start for start, end in cm_segments)

                        # CM エンコーダープロセスを起動
                        cm_return_code = await self._runEncoder(task, encoder_path, cm_encoder_options, cm_effective_duration)

                        if self._cancel_requested:
                            task.status = 'Cancelled'
                            task.encoding_finished_at = datetime.now()
                            await task.save()
                            self._cleanupOutputFiles(task)
                            logging.info(f'[EncodingQueueManager] Encoding cancelled during CM pass. [task_id: {task.id}]')
                        elif cm_return_code != 0:
                            # CM パスが失敗しても本編は完了しているので警告のみ出す
                            # 本編ファイルは残し、CM ファイルのみ削除する
                            if Path(task.cm_output_file_path).exists():
                                Path(task.cm_output_file_path).unlink()
                            task.cm_output_file_path = ''
                            logging.warning(f'[EncodingQueueManager] CM segment encoding failed, '
                                            f'but main content is intact. '
                                            f'[task_id: {task.id}, return_code: {cm_return_code}]')
                        else:
                            logging.info(f'[EncodingQueueManager] CM segment encoding completed. '
                                         f'[task_id: {task.id}, cm_output: {task.cm_output_file_path}]')

                # キャンセルされていなければ完了にする
                if not self._cancel_requested:
                    task.status = 'Completed'
                    task.progress = 100.0
                    task.encoding_finished_at = datetime.now()
                    await task.save()
                    logging.info(f'[EncodingQueueManager] Encoding completed. [task_id: {task.id}, output: {task.output_file_path}]')

        except Exception as ex:
            # 予期しないエラー
            task.status = 'Failed'
            task.fail_reason = str(ex)
            task.encoding_finished_at = datetime.now()
            await task.save()
            self._cleanupOutputFiles(task)
            logging.error(f'[EncodingQueueManager] Encoding task failed with exception. [task_id: {task.id}]', exc_info=True)

        finally:
            self._encoder_process = None
            self._current_task_id = None
            self._cancel_requested = False


    async def _runEncoder(
        self,
        task: EncodingTask,
        encoder_path: str,
        encoder_options: list[str],
        effective_duration: float,
    ) -> int:
        """
        エンコーダープロセスを起動し、進捗を監視しながら終了を待つ。
        本編エンコードと CM エンコードの両方で共通して使用される。

        Args:
            task (EncodingTask): エンコードタスク (進捗率の DB 更新に使用)
            encoder_path (str): エンコーダーのバイナリパス
            encoder_options (list[str]): エンコーダーに渡すオプション
            effective_duration (float): エンコード対象の実効時間 (秒)。
                FFmpeg の time= 出力から進捗率を算出する際の分母として使用される。
                CM 除去時は本編区間の合計時間、通常モードはソースファイルの全長。

        Returns:
            int: エンコーダープロセスの終了コード
        """

        encoder_type = task.encoder_type

        # エンコーダーコマンド全体をログに出力 (デバッグ用)
        # filter_complex の内容が長くなるため、個別にも出力する
        cmd_str = ' '.join([encoder_path, *encoder_options])
        logging.info(f'[EncodingQueueManager] Encoder command: {cmd_str}')

        self._encoder_process = await asyncio.subprocess.create_subprocess_exec(
            encoder_path, *encoder_options,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL if encoder_type == 'FFmpeg' else asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # stderr からエンコード進捗をパースしながらプロセスの完了を待つ
        assert self._encoder_process.stderr is not None
        await self._monitorProgress(task, self._encoder_process.stderr, effective_duration)

        # プロセスの終了を待つ
        return_code = await self._encoder_process.wait()
        return return_code


    def _cleanupOutputFiles(self, task: EncodingTask) -> None:
        """
        エンコード失敗・キャンセル時に中途半端な出力ファイルを削除する。
        本編ファイルと CM ファイルの両方を対象とする。

        Args:
            task (EncodingTask): エンコードタスク
        """
        if task.output_file_path and Path(task.output_file_path).exists():
            Path(task.output_file_path).unlink()
        if task.cm_output_file_path and Path(task.cm_output_file_path).exists():
            Path(task.cm_output_file_path).unlink()


    async def _getCMSections(self, task: EncodingTask) -> list[schemas.CMSection] | None:
        """
        エンコードタスクに紐づく RecordedVideo から CM 区間情報を取得する。
        CM 処理が有効 (Remove または SeparateOutput) で、かつ CM 区間が検出済みの場合のみ区間リストを返す。

        Args:
            task (EncodingTask): エンコードタスク

        Returns:
            list[schemas.CMSection] | None: CM 区間リスト。CM 処理が無効または未検出の場合は None
        """
        if task.cm_processing == 'None':
            logging.debug(f'[EncodingQueueManager] CM processing is disabled. [task_id: {task.id}]')
            return None
        if task.recorded_video_id is None:
            logging.warning(f'[EncodingQueueManager] CM processing requested but no recorded_video_id. [task_id: {task.id}]')
            return None

        recorded_video = await RecordedVideo.get_or_none(id=task.recorded_video_id)
        if recorded_video is None:
            logging.warning(f'[EncodingQueueManager] CM processing requested but RecordedVideo not found. '
                            f'[task_id: {task.id}, recorded_video_id: {task.recorded_video_id}]')
            return None
        if recorded_video.cm_sections is None:
            logging.warning(f'[EncodingQueueManager] CM processing requested but CM sections not yet analyzed. '
                            f'[task_id: {task.id}, recorded_video_id: {task.recorded_video_id}]')
            return None
        if len(recorded_video.cm_sections) == 0:
            logging.info(f'[EncodingQueueManager] CM processing requested but no CM sections detected in recording. '
                         f'[task_id: {task.id}, recorded_video_id: {task.recorded_video_id}]')
            return None

        logging.info(f'[EncodingQueueManager] Retrieved {len(recorded_video.cm_sections)} CM sections from DB. '
                     f'[task_id: {task.id}, sections: {recorded_video.cm_sections}]')
        return recorded_video.cm_sections


    def _computeKeepSegments(
        self,
        cm_sections: list[schemas.CMSection],
        duration: float,
    ) -> list[tuple[float, float]]:
        """
        CM 区間の逆 (= 本編区間) を算出する。
        CM 区間を除いた時間範囲のリストを返す。

        Args:
            cm_sections (list[schemas.CMSection]): CM 区間リスト (start_time, end_time)
            duration (float): ソースファイルの総再生時間 (秒)

        Returns:
            list[tuple[float, float]]: 本編区間のリスト (start, end)
        """
        # CM 区間を開始時刻でソート
        sorted_cms = sorted(cm_sections, key=lambda x: x['start_time'])

        keep_segments: list[tuple[float, float]] = []
        current_pos = 0.0

        for cm in sorted_cms:
            cm_start = cm['start_time']
            cm_end = cm['end_time']
            # CM 区間の前に本編がある場合
            if current_pos < cm_start:
                keep_segments.append((current_pos, cm_start))
            current_pos = cm_end

        # 最後の CM 以降に本編が残っている場合
        if current_pos < duration:
            keep_segments.append((current_pos, duration))

        # デバッグ用: 算出された本編区間をログに出力
        total_keep = sum(end - start for start, end in keep_segments)
        total_cm = duration - total_keep
        logging.info(f'[EncodingQueueManager] Keep segments computed. '
                     f'[segments: {keep_segments}, total_keep: {total_keep:.3f}s, total_cm: {total_cm:.3f}s, duration: {duration:.3f}s]')

        return keep_segments


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


    def _buildEncoderCommand(
        self,
        task: EncodingTask,
        keep_segments: list[tuple[float, float]] | None = None,
        source_frame_rate: float | None = None,
        output_path_override: str | None = None,
        video_bitrate_override: str | None = None,
    ) -> list[str]:
        """
        エンコーダーに渡すコマンドラインオプションを組み立てる。
        FFmpeg の場合は TS → MP4 のトランスコードコマンドを、
        HWEncC の場合は同様の変換コマンドを返す。
        CM 除去が有効な場合、本編区間のみをエンコードするオプションを付加する。

        SeparateOutput モードで CM 区間を別ファイルに出力する際は、output_path_override に
        CM ファイルのパスを、video_bitrate_override に CM 用のビットレートを指定する。

        Args:
            task (EncodingTask): エンコードタスク
            keep_segments (list[tuple[float, float]] | None): エンコード対象の区間リスト (開始秒, 終了秒)。
                本編エンコード時は CM を除いた本編区間、CM エンコード時は CM 区間そのもの。
            source_frame_rate (float | None): HWEncC の --trim 計算に使うソース映像のフレームレート
            output_path_override (str | None): 出力ファイルパスの上書き (CM 分離出力時に使用)
            video_bitrate_override (str | None): 映像ビットレートの上書き (CM 分離出力時に使用)

        Returns:
            list[str]: エンコーダーに渡すオプションの配列
        """

        if task.encoder_type == 'FFmpeg':
            return self._buildFFmpegCommand(task, keep_segments, output_path_override, video_bitrate_override)
        else:
            return self._buildHWEncCCommand(task, keep_segments, source_frame_rate, output_path_override, video_bitrate_override)


    def _buildFFmpegCommand(
        self,
        task: EncodingTask,
        keep_segments: list[tuple[float, float]] | None = None,
        output_path_override: str | None = None,
        video_bitrate_override: str | None = None,
    ) -> list[str]:
        """
        FFmpeg 用のコマンドラインオプションを組み立てる (TS → MP4 バッチトランスコード)。

        CM 除去が有効な場合は trim/atrim/setpts/asetpts/concat フィルターグラフを使用する。
        concat demuxer の inpoint/outpoint は TS ファイルの生の PTS (放送タイムスタンプ起点で
        通常 126144 秒付近から始まる) と比較されるため、cm_sections の再生相対秒とは一致せず
        シークが失敗する。trim フィルターはデコード後のフレームストリームに作用し、FFmpeg が
        入力時に正規化した再生相対タイムスタンプと比較するため、cm_sections の値と正確に一致する。

        SeparateOutput モードでの CM パスでは、keep_segments に CM 区間を渡し、
        output_path_override に CM ファイルパスを指定して呼び出す。

        Args:
            task (EncodingTask): エンコードタスク
            keep_segments (list[tuple[float, float]] | None): エンコード対象の区間リスト (開始秒, 終了秒)
            output_path_override (str | None): 出力ファイルパスの上書き (CM 分離出力時に使用)
            video_bitrate_override (str | None): 映像ビットレートの上書き (CM 分離出力時に使用)

        Returns:
            list[str]: FFmpeg に渡すオプションの配列
        """

        # 出力パスとビットレートをオーバーライドまたはタスクの値から取得
        output_path = output_path_override or task.output_file_path
        video_bitrate = video_bitrate_override or task.video_bitrate

        options: list[str] = []

        # 入力ファイル
        # MPEG-TS 入力の場合はフォーマットを明示的に指定する (放送 TS のコンテナ判定ミスを防ぐ)
        if task.source_file_path.lower().endswith(('.ts', '.m2ts', '.mts')):
            options.extend(['-f', 'mpegts'])
        options.extend(['-i', task.source_file_path])

        if keep_segments is not None and len(keep_segments) > 0:
            # CM 除去モード: trim/atrim フィルターで各本編区間を切り出し、setpts/asetpts で
            # タイムスタンプをリセットしてから concat フィルターで結合し、最後に yadif を適用する
            #
            # 重要: MPEG-TS の PTS は放送開始時刻基準の大きな値 (例: 126000+ 秒) から始まるため、
            # trim フィルターの start/end 秒指定とマッチしない。trim の前に setpts=PTS-STARTPTS を
            # 挿入して PTS を 0 基準に正規化することで、cm_sections の再生相対秒と正確に一致させる。
            # trim 後の setpts=PTS-STARTPTS は concat 用にタイムスタンプを区間先頭にリセットする。
            #
            # 音声ストリームは [0:a:0] で第1音声トラックのみを明示的に選択する。
            # 日本の放送 TS は主音声+副音声の2トラック構成が多く、[0:a] だと複数トラックが
            # 選択されて concat フィルターのストリーム数不一致エラーが発生する。
            filter_parts: list[str] = []
            for i, (start, end) in enumerate(keep_segments):
                # 映像: PTS を正規化してから区間を trim で切り出し、PTS を区間先頭基準にリセット
                filter_parts.append(
                    f'[0:v:0]setpts=PTS-STARTPTS,trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]'
                )
                # 音声: PTS を正規化してから区間を atrim で切り出し、PTS を区間先頭基準にリセット
                filter_parts.append(
                    f'[0:a:0]asetpts=PTS-STARTPTS,atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]'
                )

            # 各区間のラベルを結合して concat フィルターへ渡す
            n = len(keep_segments)
            concat_inputs = ''.join(f'[v{i}][a{i}]' for i in range(n))
            filter_parts.append(f'{concat_inputs}concat=n={n}:v=1:a=1[v_concat][aout]')

            # インターレース解除は concat 後に一括適用 (区間ごとに適用すると
            # 区間先頭の参照フレーム欠如で画質が劣化するため、後段でまとめて処理する)
            filter_parts.append('[v_concat]yadif=mode=0:parity=-1:deint=1[vout]')

            options.extend(['-filter_complex', ';'.join(filter_parts)])
            options.extend(['-map', '[vout]', '-map', '[aout]'])
        else:
            # 通常モード: ストリームマッピングと yadif フィルターを直接指定
            # 映像は最初のストリーム、音声は第1音声トラックを明示的に選択
            options.extend(['-map', '0:v:0', '-map', '0:a:0'])
            options.extend(['-vf', 'yadif=mode=0:parity=-1:deint=1'])
            logging.debug('[EncodingQueueManager] Normal mode (no CM removal).')

        # 映像コーデック
        if task.video_codec == 'H.265':
            options.extend(['-vcodec', 'libx265', '-profile:v', 'main'])
        else:
            options.extend(['-vcodec', 'libx264', '-profile:v', 'high'])

        # 映像ビットレートとプリセット
        options.extend(['-b:v', video_bitrate])
        options.extend(['-preset', task.quality_preset])

        # ピクセルフォーマット
        options.extend(['-pix_fmt', 'yuv420p'])

        # 音声コーデック
        options.extend(['-acodec', 'aac', '-ac', '2', '-ab', task.audio_bitrate, '-ar', '48000'])

        # 出力形式に応じたオプション
        if task.output_format == 'MKV':
            options.extend(['-f', 'matroska'])
        elif task.output_format == 'WebM':
            options.extend(['-f', 'webm'])
        else:
            # MP4: moov atom を先頭に配置してストリーミング再生を可能にする
            options.extend(['-movflags', '+faststart'])
        options.extend(['-y', output_path])

        return options


    def _buildHWEncCCommand(
        self,
        task: EncodingTask,
        keep_segments: list[tuple[float, float]] | None = None,
        source_frame_rate: float | None = None,
        output_path_override: str | None = None,
        video_bitrate_override: str | None = None,
    ) -> list[str]:
        """
        HWEncC (QSVEncC/NVEncC/VCEEncC/rkmppenc) 用のコマンドラインオプションを組み立てる。

        CM 除去が有効な場合は --trim でフレーム番号範囲を指定する。
        --seek/--seekto は連続した単一区間しか扱えず、かつ TS の生 PTS とのミスマッチで
        シーク位置が正しくない。--trim はフレーム番号ベースであり TS タイムスタンプに依存せず、
        複数区間 (カンマ区切り) も指定できるため CM 除去に適している。
        フレーム番号への変換は RecordedVideo.video_frame_rate を使って行う。

        SeparateOutput モードでの CM パスでは、keep_segments に CM 区間を渡し、
        output_path_override に CM ファイルパスを指定して呼び出す。

        Args:
            task (EncodingTask): エンコードタスク
            keep_segments (list[tuple[float, float]] | None): エンコード対象の区間リスト (開始秒, 終了秒)
            source_frame_rate (float | None): ソース映像のフレームレート (秒→フレーム変換に使用)
            output_path_override (str | None): 出力ファイルパスの上書き (CM 分離出力時に使用)
            video_bitrate_override (str | None): 映像ビットレートの上書き (CM 分離出力時に使用)

        Returns:
            list[str]: HWEncC に渡すオプションの配列
        """

        # 出力パスとビットレートをオーバーライドまたはタスクの値から取得
        output_path = output_path_override or task.output_file_path
        video_bitrate = video_bitrate_override or task.video_bitrate

        options: list[str] = []

        # 入力
        options.extend(['--input-format', 'mpegts', '-i', task.source_file_path])

        # VCEEncC は HW デコーダーが TS で不安定なため SW デコーダーを利用
        if task.encoder_type == 'VCEEncC':
            options.append('--avsw')
        else:
            options.append('--avhw')

        # CM 除去: --trim でフレーム番号範囲を指定する (複数区間カンマ区切り対応)
        # フレームレートが既知でなければ CM 除去をスキップして警告を出す
        if keep_segments is not None and len(keep_segments) > 0:
            if source_frame_rate is not None and source_frame_rate > 0:
                fps = source_frame_rate
                trim_ranges = []
                for start, end in keep_segments:
                    # 秒をフレーム番号に変換する (--trim の end は inclusive なため -1 する)
                    start_frame = int(start * fps)
                    end_frame = max(int(end * fps) - 1, start_frame)
                    trim_ranges.append(f'{start_frame}:{end_frame}')
                options.extend(['--trim', ','.join(trim_ranges)])
                logging.info(f'[EncodingQueueManager] HWEncC CM removal via --trim. '
                             f'[task_id: {task.id}, fps: {fps}, ranges: {",".join(trim_ranges)}]')
            else:
                # フレームレート不明の場合は CM 除去をスキップ
                logging.warning(f'[EncodingQueueManager] Cannot apply CM removal for HWEncC: '
                                f'source frame rate unknown. CM removal will be skipped. [task_id: {task.id}]')

        # 映像コーデック
        if task.video_codec == 'H.265':
            options.extend(['--codec', 'hevc'])
        else:
            options.extend(['--codec', 'h264'])

        # ビットレート
        options.extend(['--vbr', video_bitrate.replace('k', '')])

        # 音声設定: ステレオにダウンミックス
        options.extend(['--audio-codec', 'aac', '--audio-stream', 'stereo', '--audio-bitrate', task.audio_bitrate.replace('k', '')])

        # インターレース解除
        options.extend(['--interlace', 'tff', '--vpp-deinterlace', 'normal'])

        # 出力形式に応じたフォーマット指定
        hwenc_format_map = {'MP4': 'mp4', 'MKV': 'matroska', 'WebM': 'webm'}
        hwenc_format = hwenc_format_map.get(task.output_format, 'mp4')
        options.extend(['--output-format', hwenc_format, '-o', output_path])

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
