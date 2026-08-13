
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePath, PurePosixPath
from typing import Literal

from app import logging
from app.config import ServerSettings
from app.constants import JST
from app.utils import NormalizeToJSTDatetime
from app.utils.edcb import ReserveDataRequired
from app.utils.edcb.CtrlCmdUtil import CtrlCmdUtil


@dataclass(slots=True)
class ActiveRecordingFilePaths:
    """
    録画バックエンドが把握している録画中ファイルパスの一覧。

    Attributes:
        paths: 録画中と判定されたファイルパスの集合。
        backend: 実際に問い合わせに使ったバックエンド。
        is_reliable: バックエンドへ正常に問い合わせでき、paths が現在の録画中ファイル一覧として信頼できる場合は True。
    """

    paths: set[str]
    backend: Literal['EDCB', 'Mirakurun', 'FileSystem']
    is_reliable: bool


def _NormalizePathLikeString(path: str) -> str:
    """
    OS やバックエンドごとの区切り文字差異を吸収した比較用パス文字列を返す。

    Args:
        path (str): 正規化するパス文字列。

    Returns:
        str: 比較用に正規化されたパス文字列。
    """

    return path.replace('\\', '/').rstrip('/')


def _GetPathBasename(path: str) -> str:
    """
    OS 依存のパス区切り差異を吸収してファイル名だけを取得する。

    Args:
        path (str): ファイルパスまたはファイル名。

    Returns:
        str: ファイル名。
    """

    return PurePath(_NormalizePathLikeString(path)).name


def _IsAbsolutePathLikeString(path: str) -> bool:
    """
    OS 非依存で絶対パスらしい文字列かを判定する。

    Args:
        path (str): 判定対象のパス文字列。

    Returns:
        bool: 絶対パスらしい場合は True。
    """

    normalized_path = _NormalizePathLikeString(path)
    return (
        normalized_path.startswith('/') or
        (len(normalized_path) >= 3 and normalized_path[1] == ':' and normalized_path[2] == '/')
    )


def _ExpandRecordingPathCandidates(path: str, config: ServerSettings) -> set[str]:
    """
    録画バックエンドが返したパス文字列を KonomiTV 側の録画フォルダに対する候補パスへ展開する。

    Args:
        path (str): 録画バックエンドが返したパス文字列。
        config (ServerSettings): サーバー設定。

    Returns:
        set[str]: 比較に利用するパス候補の集合。
    """

    normalized_path = _NormalizePathLikeString(path)
    candidates = {normalized_path}

    # 録画バックエンドがファイル名や録画ルートからの相対パスだけを返す構成に備え、
    # KonomiTV 側の recorded_folders を録画ルート候補として総当たりで展開する。
    # 絶対パスらしい値はそのまま保持し、相対パスだけを recorded_folders 配下に展開する。
    if _IsAbsolutePathLikeString(normalized_path) is False:
        relative_path = PurePosixPath(normalized_path)
        for recorded_folder in config.video.recorded_folders:
            recorded_folder_path = _NormalizePathLikeString(str(recorded_folder))
            candidates.add(_NormalizePathLikeString(str(PurePosixPath(recorded_folder_path) / relative_path)))

            # バックエンド側の相対パスが録画フォルダ名を含む場合に備え、先頭要素を削った候補も作る。
            # 例: バックエンドが "recorded/foo.ts"、KonomiTV が "/mnt/recorded/foo.ts" として見ている場合。
            if len(relative_path.parts) >= 2:
                candidates.add(_NormalizePathLikeString(str(PurePosixPath(recorded_folder_path).joinpath(*relative_path.parts[1:]))))

    return candidates


def _ExpandRecordingPathCandidatesSet(paths: set[str], config: ServerSettings) -> set[str]:
    """
    録画バックエンドが返した複数のパス文字列を比較候補へ展開する。

    Args:
        paths (set[str]): 録画バックエンドが返したパス文字列の集合。
        config (ServerSettings): サーバー設定。

    Returns:
        set[str]: 比較に利用するパス候補の集合。
    """

    expanded_paths: set[str] = set()
    for path in paths:
        expanded_paths.update(_ExpandRecordingPathCandidates(path, config))
    return expanded_paths


def IsActiveRecordingFilePath(file_path: str, active_recording_paths: set[str]) -> bool:
    """
    指定されたファイルパスが録画バックエンドの録画中ファイル一覧に含まれているかを判定する。

    Args:
        file_path (str): 判定対象の録画ファイルパス。
        active_recording_paths (set[str]): 録画バックエンドから取得した録画中ファイルパスの集合。

    Returns:
        bool: 録画中ファイル一覧に含まれている場合は True。
    """

    normalized_file_path = _NormalizePathLikeString(file_path)
    normalized_active_paths = {_NormalizePathLikeString(active_path) for active_path in active_recording_paths}
    if normalized_file_path in normalized_active_paths:
        return True

    # 録画バックエンドと KonomiTV が別ホストで動く場合、録画フォルダのマウントポイントだけが異なることがある。
    # その場合でも末尾のパスが一致していれば同じ録画ファイルとみなす。
    for active_path in normalized_active_paths:
        if normalized_file_path.endswith('/' + active_path) or active_path.endswith('/' + normalized_file_path):
            return True

    # 最後のフォールバックとして、録画中ファイル一覧内でファイル名が一意な場合のみファイル名一致を許可する。
    # 同名ファイルが複数ある状態で basename だけに頼ると誤判定になり得るため、その場合は一致させない。
    file_basename = _GetPathBasename(normalized_file_path)
    active_basenames = [_GetPathBasename(active_path) for active_path in normalized_active_paths]
    return active_basenames.count(file_basename) == 1 and file_basename in active_basenames


def _ShouldCheckEDCBRecordingInProgress(reserve_data: ReserveDataRequired) -> bool:
    """
    録画中判定のために EDCB へ追加問い合わせを行うべき予約かを判定する。

    Args:
        reserve_data (ReserveDataRequired): 判定対象の予約情報。

    Returns:
        bool: 録画中判定を行うべき場合は True。
    """

    # 無効予約・視聴予約は録画ファイルパスが存在しないため、判定 API を呼ばない。
    rec_mode = reserve_data.get('rec_setting', {}).get('rec_mode', 1)
    if rec_mode >= 5 or rec_mode == 4:
        return False

    # 録画中判定を行う時間範囲 (現在時刻の2時間前〜2時間後) に絞る。
    # 予約一覧全件に対して sendGetRecFilePath() を実行すると EDCB 側の負荷が大きいため、現実的に録画中になり得る予約だけに限定する。
    current_time = datetime.now(tz=JST)
    recording_check_start = current_time - timedelta(hours=2)
    recording_check_end = current_time + timedelta(hours=2)

    reserve_start_time = NormalizeToJSTDatetime(reserve_data['start_time'])
    reserve_end_time = reserve_start_time + timedelta(seconds=reserve_data['duration_second'])

    return reserve_start_time <= recording_check_end and reserve_end_time >= recording_check_start


async def _GetActiveRecordingFilePathsFromEDCB() -> ActiveRecordingFilePaths:
    """
    EDCB から現在録画中のファイルパス一覧を取得する。

    Returns:
        ActiveRecordingFilePaths: EDCB から取得した録画中ファイルパス一覧。
    """

    edcb = CtrlCmdUtil()
    reserve_data_list = await edcb.sendEnumReserve()
    if reserve_data_list is None:
        logging.warning('[RecordingStatusProvider][EDCB] Failed to get recording reservations.')
        return ActiveRecordingFilePaths(paths=set(), backend='EDCB', is_reliable=False)

    active_paths: set[str] = set()
    for reserve_data in reserve_data_list:
        if _ShouldCheckEDCBRecordingInProgress(reserve_data) is False:
            continue
        rec_file_path = await edcb.sendGetRecFilePath(reserve_data['reserve_id'])
        if rec_file_path is not None:
            active_paths.add(rec_file_path)

    return ActiveRecordingFilePaths(paths=active_paths, backend='EDCB', is_reliable=True)


async def _GetActiveRecordingFilePathsFromMirakurun(config: ServerSettings) -> ActiveRecordingFilePaths:
    """
    Mirakurun バックエンドの録画エンジンから、現在録画中のファイルパス一覧を取得する。

    Mirakurun バックエンドでは KonomiTV 自身が MirakurunRecordingTask で録画を実行しており、
    録画中の予約は MirakurunReservation に status='Recording' として記録されている。
    そのため EDCB のように外部プロセスへ問い合わせる必要がなく、DB から直接取得できる。

    Args:
        config (ServerSettings): サーバー設定。

    Returns:
        ActiveRecordingFilePaths: 録画中ファイルパス一覧。
    """

    # 循環インポートを避けるため、関数内でモデルをインポートする
    ## RecordingStatusProvider は app.config にのみ依存する設計とし、モデル層への依存をモジュール読み込み時に持ち込まない
    from app.models.MirakurunReservation import MirakurunReservation

    try:
        # 録画中の予約のうち、録画ファイルパスが確定しているものだけを取得する
        ## 録画開始直後などでファイルパスが未確定の予約は、追っかけ再生の対象にもなり得ないため除外する
        recording_reservations = await MirakurunReservation.filter(
            status = 'Recording',
            recording_file_path__not_isnull = True,
        ).all()
    except Exception as ex:
        logging.warning('[RecordingStatusProvider][Mirakurun] Failed to get recording reservations.', exc_info=ex)
        return ActiveRecordingFilePaths(paths=set(), backend='Mirakurun', is_reliable=False)

    active_paths: set[str] = set()
    for reservation in recording_reservations:
        if reservation.recording_file_path is not None:
            active_paths.add(reservation.recording_file_path)

    logging.debug(f'[RecordingStatusProvider][Mirakurun] Active recording paths: {len(active_paths)}')
    return ActiveRecordingFilePaths(
        paths = _ExpandRecordingPathCandidatesSet(active_paths, config),
        backend = 'Mirakurun',
        is_reliable = True,
    )


async def GetActiveRecordingFilePaths(config: ServerSettings) -> ActiveRecordingFilePaths:
    """
    現在のバックエンドから録画中ファイルパス一覧を取得する。

    Args:
        config (ServerSettings): サーバー設定。

    Returns:
        ActiveRecordingFilePaths: 録画中ファイルパス一覧。
    """

    if config.general.backend == 'EDCB':
        return await _GetActiveRecordingFilePathsFromEDCB()
    if config.general.backend == 'Mirakurun':
        return await _GetActiveRecordingFilePathsFromMirakurun(config)

    # バックエンドへ問い合わせられない場合は、ファイルの更新時刻など呼び出し側のヒューリスティックに委ねる
    return ActiveRecordingFilePaths(paths=set(), backend='FileSystem', is_reliable=False)
