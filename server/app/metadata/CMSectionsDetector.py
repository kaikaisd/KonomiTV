
from __future__ import annotations

import asyncio
import pathlib
import re
import shutil
import tempfile
import time

import anyio
import typer

from app import logging, schemas
from app.config import LoadConfig
from app.constants import LIBRARY_PATH
from app.metadata.CMAnalyzer import (
    CMAnalyzerRequest,
    CMContainerFormat,
    GenericCMAnalyzer,
)
from app.models.RecordedVideo import RecordedVideo


class CMSectionsDetector:
    """
    録画 TS ファイルに含まれる CM 区間を検出するクラス
    録画ファイルと同じファイル名で .chapter.txt が保存されていればそこから CM 区間情報を取得し、
    .chapter.txt が存在しない場合は自前で CM 区間を検出する
    """

    def __init__(
        self,
        file_path: anyio.Path,
        duration_sec: float,
        container_format: CMContainerFormat = 'MPEG-TS',
        service_id: int | None = None,
    ) -> None:
        """
        録画 TS ファイルに含まれる CM 区間を検出するクラスを初期化する

        Args:
            file_path (anyio.Path): 動画ファイルのパス
            duration_sec (float): 動画の再生時間(秒)
            container_format (CMContainerFormat): 動画ファイルのコンテナ形式
            service_id (int | None): 録画対象のサービス ID
        """

        self.file_path = file_path
        self.duration_sec = duration_sec
        # FFmpeg / FFprobe の入力 demuxer 選択に使うコンテナ形式
        self.container_format: CMContainerFormat = container_format
        # 複数サービスを含む入力から録画対象のストリームを選ぶためのサービス ID
        self.service_id = service_id


    async def detectAndSave(self) -> None:
        """
        録画ファイルの CM 区間を検出し、データベースに保存する
        """

        start_time = time.time()
        logging.info(f'{self.file_path}: Detecting CM sections...')
        try:
            # 録画ファイルに対応するチャプターファイル (.chapter.txt) がもしあれば解析し、CM 区間情報を取得する
            ## 自前で解析すると計算コストが高いので、もしチャプターファイルがあればそれを優先的に使う
            ## .chapter.txt は Amatsukaze でエンコードした際に設定次第で自動生成される
            cm_sections = await self.__detectFromChapterFile()

            # チャプターファイルが存在しない場合、join_logo_scp (with chapter_exe) での解析を試みる
            ## ロゴと無音・シーンチェンジを併用するため silencedetect より精度が高いが、
            ## thirdparty/CMAnalysis 以下の専用ランタイム (Linux x64 のみ提供) を必要とする
            if not cm_sections:
                cm_sections = await self.__detectWithJLS()

            # 専用ランタイムが未導入の環境 (Windows など) や JLS が失敗した場合は、
            ## FFmpeg の silencedetect による従来の検出へフォールバックする
            ## これにより、ランタイムを導入していない環境でも従来通りの精度で CM 区間を検出できる
            if not cm_sections:
                cm_sections = await self.__detectWithFFmpeg()

            # 自前でも解析できなかった（解析に失敗した）or CM 区間が1つも検出されなかった場合、
            # バックグラウンド解析処理が再度実行された際の再解析を回避するために [] を設定する
            ## [] は解析したが CM 区間がなかった/検出に失敗したことを表す
            ## CM 区間解析はかなり計算コストが高い処理のため、一度解析に失敗した録画ファイルは再解析しない
            if cm_sections is None:
                cm_sections = []

            # 検出結果をログに出力
            for cm_section in cm_sections:
                logging.debug(f'{self.file_path}: CM section detected: {cm_section["start_time"]} - {cm_section["end_time"]}')

            # 検出結果をデータベースに保存
            ## ファイルパスから対応する RecordedVideo レコードを取得
            db_recorded_video = await RecordedVideo.get_or_none(file_path=str(self.file_path))
            if db_recorded_video is not None:
                # CM 区間情報を更新
                # 検出できなかった場合も必ず [] を設定する
                # update_fields を指定して cm_sections フィールドのみを更新することで、
                # KeyFrameAnalyzer や ThumbnailGenerator と同時実行した際に
                # 互いのフィールドを上書きしてしまうレースコンディションを防ぐ
                db_recorded_video.cm_sections = cm_sections
                await db_recorded_video.save(update_fields=['cm_sections'])
                if len(cm_sections) > 0:
                    logging.info(f'{self.file_path}: Saved {len(cm_sections)} CM sections. ({time.time() - start_time:.2f} sec)')
                else:
                    logging.info(f'{self.file_path}: No CM sections detected. ({time.time() - start_time:.2f} sec)')
            else:
                logging.warning(f'{self.file_path}: RecordedVideo record not found.')

        except Exception as ex:
            logging.error(f'{self.file_path}: Error saving CM sections to DB:', exc_info=ex)


    async def __detectWithJLS(self) -> list[schemas.CMSection] | None:
        """
        録画ファイルの CM 区間を join_logo_scp (with chapter_exe) を使って解析する

        thirdparty/CMAnalysis 以下の専用ランタイムを必要とし、未導入の環境では常に None を返す。
        その場合は呼び出し元が silencedetect による検出へフォールバックする。

        Returns:
            list[schemas.CMSection] | None: 解析に成功した場合は CM 区間のリストを返す。
                ランタイム未導入・解析失敗の場合は None を返す。
        """

        # GenericCMAnalyzer を OS の一時領域で実行する
        ## 録画フォルダは読み取り専用でマウントされる構成も正式にサポートするため、
        ## 録画ファイルの隣には一時ディレクトリも解析結果も作成しない
        ## 映像は FFmpeg で Matroska へ stream-copy し、音声だけ固定 PCM へ正規化してから
        ## chapter_exe / logoframe / join_logo_scp に渡すため、サーバー側で映像エンコードは行わない
        work_directory = pathlib.Path(tempfile.mkdtemp(
            prefix=f'.{self.file_path.stem}.konomitv-cm-',
        ))
        try:
            result = await GenericCMAnalyzer().analyze(CMAnalyzerRequest(
                recorded_file_path=pathlib.Path(str(self.file_path)),
                work_directory=work_directory,
                service_id=self.service_id,
                hardware_device=self.__resolveHardwareDecodeDevice(),
                duration_seconds=self.duration_sec,
                container_format=self.container_format,
            ))
            if result.status != 'completed':
                logging.warning(
                    f'{self.file_path}: CM analysis with JLS did not complete. '
                    f'[status: {result.status}] [error_code: {result.error_code}] '
                    f'[error_message: {result.error_message}]'
                )
                return None

            # 解析結果は録画時間を超える区間を含みうるため、録画時間でクランプしてから返す
            return [schemas.CMSection(
                start_time=section['start_time'],
                end_time=min(section['end_time'], float(self.duration_sec)),
            ) for section in result.sections if section['start_time'] < float(self.duration_sec)]
        finally:
            await asyncio.to_thread(shutil.rmtree, work_directory, ignore_errors=True)


    @staticmethod
    def __resolveHardwareDecodeDevice() -> str | None:
        """
        CM 解析で優先する Linux VAAPI render device を返す

        Returns:
            str | None: 利用可能な render device のパス。存在しない場合は None。
        """

        # コンテナ環境では公開された render node だけが見えるため、番号を固定せず列挙する
        ## FFMS2 側で初期化に失敗した場合は GenericCMAnalyzer が CPU で一度だけ再試行する
        dri_directory = pathlib.Path('/dev/dri')
        if dri_directory.is_dir() is False:
            return None
        render_devices = sorted(str(device) for device in dri_directory.glob('renderD*'))
        return render_devices[0] if render_devices else None


    async def __detectWithFFmpeg(self) -> list[schemas.CMSection] | None:
        """
        FFmpeg の silencedetect フィルターを使って録画ファイルの CM 区間を自動検出する

        日本のテレビ CM の特徴を利用して CM 区間を検出する:
        - CM は 15秒 / 30秒 / 60秒 / 90秒 のいずれかの長さ
        - CM と CM の間は無音区間で区切られる
        - CM は連続して複数本流れる (CM ブロック)

        検出アルゴリズム:
        1. FFmpeg の silencedetect で無音区間を検出する
        2. 無音区間の中間点をセグメント境界とし、動画を複数セグメントに分割する
        3. 各セグメントの長さが CM の標準的な長さ (15s/30s/60s/90s) に一致するか判定する
        4. CM 長に一致するセグメントが 2つ以上連続している区間を CM ブロックとして検出する

        Returns:
            list[schemas.CMSection] | None: 解析に成功した場合は CM 区間のリストを返す。
                解析に失敗した場合は None を返す。
        """

        # 無音区間を検出するための FFmpeg コマンドを構築
        # silencedetect: 無音区間を検出するフィルター
        #   noise=-40dB: 無音とみなす閾値 (日本の放送では CM 境界の無音は非常に静か)
        #   d=0.3: 最低 0.3 秒以上の無音を検出対象とする (短すぎる無音を除外)
        # -vn: 映像処理をスキップし音声のみ処理する (高速化)
        # -f null: 出力は不要なので /dev/null に捨てる
        ffmpeg_command = [
            LIBRARY_PATH['FFmpeg'],
            '-i', str(self.file_path),
            '-vn',
            '-af', 'silencedetect=noise=-40dB:d=0.3',
            '-f', 'null',
            '-',
        ]

        logging.info(f'{self.file_path}: Running FFmpeg silencedetect for CM detection...')

        try:
            # FFmpeg を非同期で実行し、stderr から silencedetect の出力を取得する
            # silencedetect の検出結果は stderr に出力される
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr_bytes = await process.communicate()
            stderr_output = stderr_bytes.decode('utf-8', errors='replace')

            if process.returncode != 0:
                logging.error(f'{self.file_path}: FFmpeg silencedetect failed with return code {process.returncode}.')
                return None

        except Exception as ex:
            logging.error(f'{self.file_path}: Failed to run FFmpeg silencedetect:', exc_info=ex)
            return None

        # silencedetect の出力から無音区間を抽出する
        # 出力フォーマット例:
        #   [silencedetect @ 0x...] silence_start: 123.456
        #   [silencedetect @ 0x...] silence_end: 124.789 | silence_duration: 1.333
        silence_sections = self.__parseSilenceDetectOutput(stderr_output)
        logging.info(f'{self.file_path}: Detected {len(silence_sections)} silence sections.')

        if len(silence_sections) == 0:
            # 無音区間が1つも検出されなかった場合は CM 検出不可
            return None

        # 無音区間の中間点をセグメント境界として、動画をセグメントに分割する
        # 各セグメントは (start_time, end_time) のタプル
        segments = self.__buildSegmentsFromSilence(silence_sections)
        logging.debug(f'{self.file_path}: Built {len(segments)} segments from silence boundaries.')

        # 各セグメントが CM の標準的な長さに一致するか判定し、CM ブロックを検出する
        cm_sections = self.__detectCMBlocks(segments)
        logging.info(f'{self.file_path}: Detected {len(cm_sections)} CM blocks from silence analysis.')

        return cm_sections


    def __parseSilenceDetectOutput(self, stderr_output: str) -> list[tuple[float, float]]:
        """
        FFmpeg silencedetect フィルターの stderr 出力を解析し、無音区間のリストを返す

        Args:
            stderr_output (str): FFmpeg の stderr 出力テキスト

        Returns:
            list[tuple[float, float]]: 無音区間の (start, end) タプルのリスト
        """

        silence_sections: list[tuple[float, float]] = []

        # silence_start と silence_end を正規表現で抽出する
        # silence_start: 開始時刻
        # silence_end: 終了時刻 (silence_duration は不要)
        start_pattern = re.compile(r'silence_start:\s*([\d.]+)')
        end_pattern = re.compile(r'silence_end:\s*([\d.]+)')

        # silence_start と silence_end は交互に出現するので、start を保持しておき end が来たらペアにする
        current_start: float | None = None
        for line in stderr_output.split('\n'):
            start_match = start_pattern.search(line)
            end_match = end_pattern.search(line)

            if start_match:
                current_start = float(start_match.group(1))
            if end_match and current_start is not None:
                silence_end = float(end_match.group(1))
                silence_sections.append((current_start, silence_end))
                current_start = None

        return silence_sections


    def __buildSegmentsFromSilence(self, silence_sections: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """
        無音区間の中間点をセグメント境界として、動画をセグメントに分割する

        無音区間の中間点を境界として使う理由:
        - CM と本編の境界は無音区間の「途中」にあることが多い
        - 無音の中間点を取ることで、CM の開始/終了が正確な秒数 (15s, 30s 等) に近づく

        Args:
            silence_sections (list[tuple[float, float]]): 無音区間の (start, end) タプルのリスト

        Returns:
            list[tuple[float, float]]: セグメントの (start_time, end_time) タプルのリスト
        """

        # 無音区間の中間点をセグメント境界とする
        boundaries: list[float] = []
        for silence_start, silence_end in silence_sections:
            midpoint = (silence_start + silence_end) / 2.0
            boundaries.append(midpoint)

        # 動画の先頭 (0.0) と末尾 (duration_sec) を境界リストに追加する
        # これにより、最初のセグメントは 0.0 〜 最初の無音中間点、最後のセグメントは最後の無音中間点 〜 動画末尾となる
        all_boundaries = [0.0, *boundaries, self.duration_sec]

        # 隣接する境界点のペアをセグメントとして返す
        segments: list[tuple[float, float]] = []
        for i in range(len(all_boundaries) - 1):
            seg_start = all_boundaries[i]
            seg_end = all_boundaries[i + 1]
            # 極端に短いセグメント (0.5秒未満) は無視する
            # 連続する無音区間が近接している場合にゴミセグメントが生じるのを防ぐ
            if seg_end - seg_start >= 0.5:
                segments.append((seg_start, seg_end))

        return segments


    def __detectCMBlocks(self, segments: list[tuple[float, float]]) -> list[schemas.CMSection]:
        """
        セグメントの長さのパターンから CM ブロックを検出する

        日本のテレビ CM は 15秒 / 30秒 / 60秒 / 90秒 のいずれかの長さである。
        CM は複数本連続して流れるため、CM 長に一致するセグメントが 2つ以上連続している区間を CM ブロックとみなす。

        Args:
            segments (list[tuple[float, float]]): セグメントの (start_time, end_time) タプルのリスト

        Returns:
            list[schemas.CMSection]: 検出された CM 区間のリスト
        """

        # CM の標準的な長さ (秒)
        CM_DURATIONS = [15.0, 30.0, 60.0, 90.0]
        # CM 長との一致判定に使う許容誤差 (秒)
        # 無音区間の中間点を使うため、多少のずれが生じる
        TOLERANCE = 1.5

        # 各セグメントが CM の長さに一致するかどうかを判定する
        is_cm_duration: list[bool] = []
        for seg_start, seg_end in segments:
            duration = seg_end - seg_start
            # いずれかの CM 標準長に許容誤差以内で一致するか判定
            matches = any(abs(duration - cm_dur) <= TOLERANCE for cm_dur in CM_DURATIONS)
            is_cm_duration.append(matches)
            # デバッグ用: 各セグメントの長さと CM 判定結果をログに出力
            logging.debug(f'{self.file_path}: Segment {len(is_cm_duration)-1}: '
                          f'{seg_start:.3f}-{seg_end:.3f} ({duration:.3f}s) -> CM={matches}')

        # CM 長に一致するセグメントが連続している区間 (ラン) を検出する
        # 連続数が 2 以上のランを CM ブロックとして採用する
        cm_sections: list[schemas.CMSection] = []
        i = 0
        while i < len(segments):
            if is_cm_duration[i]:
                # CM 長セグメントの連続区間の開始
                run_start = i
                # 連続する CM 長セグメントを数える
                while i < len(segments) and is_cm_duration[i]:
                    i += 1
                run_end = i  # run_end は排他的 (最後の CM 長セグメントのインデックス + 1)
                run_length = run_end - run_start

                # 末尾の短いセグメントを CM ブロックに吸収する処理
                # 録画が CM の途中で終了した場合や、CM 後に短い無音区間が残っている場合、
                # 最後のセグメントが CM 標準長に一致しないため連続ランが途切れてしまう。
                # 末尾のセグメントが短い (10秒未満) 場合、CM ブロックの一部として扱う。
                if run_end < len(segments):
                    trailing_seg = segments[run_end]
                    trailing_duration = trailing_seg[1] - trailing_seg[0]
                    # 末尾が動画の最後に近く (残り5秒以内) かつ短い場合は吸収する
                    if trailing_duration < 10.0 and (self.duration_sec - trailing_seg[1]) < 5.0:
                        run_end += 1
                        i = run_end

                # 2つ以上連続している場合のみ CM ブロックとして採用する
                # 本編中にたまたま 30秒ぴったりのセグメントが1つだけ存在することはあり得るが、
                # 2つ以上連続するのは CM ブロックの特徴的なパターン
                if run_length >= 2:
                    cm_block_start = segments[run_start][0]
                    cm_block_end = segments[run_end - 1][1]

                    # CM ブロックの合計時間が最低 30秒以上であることを確認する
                    # 15秒 CM が 2つ連続しただけでも 30秒になるため、このしきい値は保守的
                    cm_block_duration = cm_block_end - cm_block_start
                    if cm_block_duration >= 30.0:
                        cm_sections.append(schemas.CMSection(
                            start_time=round(cm_block_start, 3),
                            end_time=round(cm_block_end, 3),
                        ))
            else:
                i += 1

        # 動画の先頭付近 (最初の5秒以内に開始) の CM ブロックは除外する
        # 番組冒頭のジングルや提供クレジットが CM として誤検出されることがあるため
        # ただし、録画開始直後から CM が始まっているケースもあるため、
        # CM ブロックの長さが 60秒以上であれば残す (短い誤検出だけ除外)
        if cm_sections and cm_sections[0]['start_time'] < 5.0:
            first_block_duration = cm_sections[0]['end_time'] - cm_sections[0]['start_time']
            if first_block_duration < 60.0:
                cm_sections = cm_sections[1:]

        return cm_sections


    async def __detectFromChapterFile(self) -> list[schemas.CMSection] | None:
        """
        録画ファイルに対応するチャプターファイルがもしあれば解析し、CM 区間情報を取得する

        Returns:
            list[CMSection] | None: チャプターファイルが存在し、解析に成功した場合は CM 区間のリストを返す
        """

        # チャプターファイルのパスを生成
        # 録画ファイルが hoge.ts なら hoge.chapter.txt を探す
        chapter_file_path = self.file_path.with_name(f"{self.file_path.stem}.chapter.txt")

        # チャプターファイルが存在しない場合は None を返す
        if not await chapter_file_path.exists():
            return None

        # チャプターファイルを読み込む
        try:
            async with await chapter_file_path.open(encoding='utf-8') as f:
                lines = await f.readlines()
        except Exception as ex:
            # チャプターファイルの読み込みに失敗した場合は None を返す
            logging.error(f'{chapter_file_path}: Failed to read chapter file:', exc_info=ex)
            return None

        # チャプター情報を格納するリスト
        chapters: list[tuple[int, str, float]] = []  # (番号, 名前, 時刻)
        cm_sections: list[schemas.CMSection] = []

        # 2行ずつ処理 (チャプター時刻行とチャプター名行)
        for i in range(0, len(lines), 2):
            if i + 1 >= len(lines):
                break

            time_line = lines[i].strip()
            name_line = lines[i + 1].strip()

            # チャプター行のフォーマットが不正な場合は採用しない
            # 当該行だけ飛ばすこともできるが整合性が崩れる可能性が高いため、自前で CM 区間を検出した方が確実
            if not (time_line.startswith('CHAPTER') and name_line.startswith('CHAPTER') and 'NAME' in name_line):
                return None

            try:
                # チャプター番号を取得
                chapter_num = int(time_line[7:9])
                # チャプター時刻を取得
                chapter_time = self.__timeToSeconds(time_line.split('=')[1])
                # チャプター名を取得
                chapter_name = name_line.split('=')[1]

                if chapter_time <= float(self.duration_sec):
                    chapters.append((chapter_num, chapter_name, chapter_time))
                else:
                    # チャプター時刻が動画長を超えている行は無視する
                    logging.warning(f'{chapter_file_path}: Chapter time {chapter_time} exceeds the video duration {self.duration_sec}. Skipping.')
            except Exception as ex:
                # パースに失敗した場合は採用しない
                # 当該行だけ飛ばすこともできるが整合性が崩れる可能性が高いため、自前で CM 区間を検出した方が確実
                logging.warning(f'{chapter_file_path}: Failed to parse chapter data. (line {i}-{i+1}): {time_line}, {name_line}', exc_info=ex)
                return None

        # CM 区間を検出
        current_cm_start: float | None = None

        for i, (_, name, ctime) in enumerate(chapters):
            # CM 開始位置を検出
            if name.startswith('CM') and current_cm_start is None:
                current_cm_start = ctime
            # CM 終了位置を検出
            elif not name.startswith('CM') and current_cm_start is not None:
                cm_sections.append({
                    'start_time': current_cm_start,
                    'end_time': ctime,
                })
                current_cm_start = None

        # 最後のチャプターが CM で終わっている場合、動画長を終了時刻とする
        if current_cm_start is not None:
            cm_sections.append({
                'start_time': current_cm_start,
                'end_time': float(self.duration_sec),
            })

        return cm_sections


    @staticmethod
    def __timeToSeconds(time_str: str) -> float:
        """
        時刻文字列 (HH:MM:SS.mmm) を秒単位の float に変換する

        Args:
            time_str (str): 時刻文字列 (HH:MM:SS.mmm)

        Returns:
            float: 秒単位の時刻
        """

        # 時、分、秒をそれぞれ分割
        hours, minutes, seconds = time_str.strip().split(':')
        # 時と分は整数に、秒は小数に変換して合計を返す
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)


if __name__ == "__main__":
    # デバッグ用: 録画ファイルの CM 区間を検出する
    # Usage: poetry run python -m app.metadata.CMSectionsDetector /path/to/recorded_file.ts
    def main(
        file_path: pathlib.Path = typer.Argument(
            ...,
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="録画ファイルのパス",
        ),
    ) -> None:
        """
        録画ファイルの CM 区間を検出する
        """

        # 設定を読み込む (必須)
        LoadConfig(bypass_validation=True)

        # メタデータを解析
        from app.metadata.MetadataAnalyzer import MetadataAnalyzer
        analyzer = MetadataAnalyzer(file_path)
        recorded_program = analyzer.analyze()
        if recorded_program is None:
            print(f'Error: {file_path} is not a valid recorded file.')
            return

        # CMSectionsDetector を初期化
        detector = CMSectionsDetector(
            file_path = anyio.Path(recorded_program.recorded_video.file_path),
            duration_sec = recorded_program.recorded_video.duration,
            container_format = recorded_program.recorded_video.container_format,
            service_id = recorded_program.service_id,
        )

        # CM 区間を検出
        asyncio.run(detector.detectAndSave())

    typer.run(main)
