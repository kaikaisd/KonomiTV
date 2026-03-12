
import errno
import io
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, cast

import puremagic
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from PIL import Image, ImageOps

from app import logging, schemas
from app.config import Config
from app.models.CaptureBookmark import CaptureBookmark
from app.models.CaptureFolder import CaptureFolder
from app.models.Channel import Channel
from app.models.User import User
from app.routers.UsersRouter import GetCurrentUser


# ルーター
router = APIRouter(
    tags = ['Captures'],
    prefix = '/api/captures',
)

# キャプチャ一覧 API の1ページあたりの表示件数
# グリッドの列数 (デスクトップ: 4列, スマホ横: 3列, スマホ縦: 2列) の公倍数にすることで、
# 最終行が中途半端な列数にならないようにする (4, 3, 2 の最小公倍数は 12)
PAGE_SIZE = 36

# サムネイル画像の最大サイズ (長辺のピクセル数)
THUMBNAIL_MAX_SIZE = 400

# キャプチャ画像として認識する拡張子
CAPTURE_EXTENSIONS = {'.jpg', '.jpeg', '.png'}


def GetUploadFolders() -> list[Path]:
    """
    サーバー設定からキャプチャの保存先フォルダのリストを取得する。
    存在しないフォルダは除外して返す。

    Returns:
        存在する保存先フォルダのパスのリスト
    """
    return [Path(folder) for folder in Config().capture.upload_folders if Path(folder).exists()]


def FindCaptureFile(filename: str) -> Path | None:
    """
    指定されたファイル名のキャプチャ画像を保存先フォルダから検索する。
    ディレクトリトラバーサル対策を含む。

    Args:
        filename: 検索するキャプチャ画像のファイル名

    Returns:
        キャプチャ画像のフルパス (見つからなかった場合は None)
    """

    upload_folders = GetUploadFolders()
    filename_path = Path(filename)

    for upload_folder in upload_folders:
        # ディレクトリトラバーサル対策のためのチェック
        ## ref: https://stackoverflow.com/a/45190125/17124142
        try:
            upload_folder.joinpath(filename_path).resolve().relative_to(upload_folder.resolve())
        except ValueError:
            # トラバーサルが検出された場合は None を返す
            return None

        filepath = upload_folder / filename_path
        if filepath.is_file():
            return filepath

    return None


def ExtractCaptureInfo(filepath: Path) -> schemas.Capture:
    """
    キャプチャ画像ファイルからメタデータを抽出し、Capture スキーマを生成する。
    画像の幅・高さと EXIF XPComment フィールドに格納された JSON メタデータを読み取る。

    Args:
        filepath: キャプチャ画像のフルパス

    Returns:
        キャプチャ画像のメタデータを含む Capture スキーマ
    """

    # ファイルの基本情報を取得
    stat = filepath.stat()
    file_size = stat.st_size
    file_modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

    # 拡張子から MIME タイプを判定
    suffix = filepath.suffix.lower()
    if suffix in ('.jpg', '.jpeg'):
        mime_type: Literal['image/jpeg', 'image/png'] = 'image/jpeg'
    else:
        mime_type = 'image/png'

    # 画像を開いて幅・高さを取得し、EXIF メタデータを抽出する
    image_width = 0
    image_height = 0
    capture_metadata: schemas.CaptureMetadata | None = None
    try:
        with Image.open(filepath) as img:
            image_width = img.width
            image_height = img.height

            # EXIF データから XPComment (タグ番号 0x9C9C = 40092) を読み取る
            ## CaptureCompositor が UCS-2 (UTF-16-LE) エンコードされた JSON を XPComment に格納している
            exif_data = img.getexif()
            xp_comment_tag = 0x9C9C  # XPComment タグ番号
            if xp_comment_tag in exif_data:
                xp_comment_raw = exif_data[xp_comment_tag]
                # Pillow は XPComment を bytes として返す場合と str として返す場合がある
                if isinstance(xp_comment_raw, bytes):
                    # UCS-2 (UTF-16-LE) でデコードし、末尾のヌル文字を除去する
                    xp_comment_str = xp_comment_raw.decode('utf-16-le').rstrip('\x00')
                else:
                    xp_comment_str = str(xp_comment_raw).rstrip('\x00')

                # JSON としてパースし、CaptureMetadata スキーマに変換する
                try:
                    metadata_dict = json.loads(xp_comment_str)
                    capture_metadata = schemas.CaptureMetadata(**metadata_dict)
                except (json.JSONDecodeError, Exception) as ex:
                    # JSON のパースに失敗した場合はメタデータなしとして扱う
                    logging.debug(f'[CapturesRouter][ExtractCaptureInfo] Failed to parse EXIF XPComment for {filepath.name}: {ex}')
    except Exception as ex:
        # 画像のオープンに失敗した場合はデフォルト値で続行する
        logging.warning(f'[CapturesRouter][ExtractCaptureInfo] Failed to open image {filepath.name}: {ex}')

    return schemas.Capture(
        filename = filepath.name,
        file_size = file_size,
        file_modified_at = file_modified_at,
        mime_type = mime_type,
        image_width = image_width,
        image_height = image_height,
        capture_metadata = capture_metadata,
    )


def ExtractCaptureMetadataOnly(filepath: Path) -> schemas.CaptureMetadata | None:
    """
    キャプチャ画像ファイルから EXIF XPComment のメタデータのみを軽量に抽出する。
    画像のピクセルデータはデコードせず、EXIF ヘッダーのみ読み取ることで高速化を図る。
    検索・フィルタリング時の判定に使用する。

    Args:
        filepath: キャプチャ画像のフルパス

    Returns:
        CaptureMetadata スキーマ (EXIF がない場合は None)
    """

    try:
        with Image.open(filepath) as img:
            exif_data = img.getexif()
            xp_comment_tag = 0x9C9C
            if xp_comment_tag in exif_data:
                xp_comment_raw = exif_data[xp_comment_tag]
                if isinstance(xp_comment_raw, bytes):
                    xp_comment_str = xp_comment_raw.decode('utf-16-le').rstrip('\x00')
                else:
                    xp_comment_str = str(xp_comment_raw).rstrip('\x00')
                try:
                    metadata_dict = json.loads(xp_comment_str)
                    return schemas.CaptureMetadata(**metadata_dict)
                except (json.JSONDecodeError, Exception):
                    pass
    except Exception:
        pass
    return None


def CollectCaptureFiles() -> list[tuple[str, float, Path]]:
    """
    すべての保存先フォルダからキャプチャ画像ファイルを収集する。
    os.scandir() を使うことで、ファイルの stat 情報を効率的に取得する。
    同じファイル名が複数のフォルダに存在する場合は最初に見つかったものを優先する。

    Returns:
        (ファイル名, 更新日時, フルパス) のタプルのリスト
    """

    upload_folders = GetUploadFolders()
    capture_files: list[tuple[str, float, Path]] = []
    seen_filenames: set[str] = set()

    for upload_folder in upload_folders:
        try:
            with os.scandir(upload_folder) as entries:
                for entry in entries:
                    # ディレクトリはスキップ
                    if not entry.is_file():
                        continue
                    # キャプチャ画像の拡張子でないファイルはスキップ
                    name_lower = entry.name.lower()
                    if not any(name_lower.endswith(ext) for ext in CAPTURE_EXTENSIONS):
                        continue
                    # 同じファイル名が既に登録済みならスキップ (最初に見つかったフォルダを優先)
                    if entry.name in seen_filenames:
                        continue
                    seen_filenames.add(entry.name)
                    # ファイルの更新日時を取得
                    stat = entry.stat()
                    capture_files.append((entry.name, stat.st_mtime, Path(entry.path)))
        except OSError as ex:
            logging.warning(f'[CapturesRouter][CollectCaptureFiles] Failed to scan folder {upload_folder}: {ex}')
            continue

    return capture_files


# ==================== キャプチャ一覧 API ====================

@router.get(
    '',
    summary = 'キャプチャ一覧 API',
    response_model = schemas.Captures,
)
async def CaptureListAPI(
    order: Annotated[Literal['desc', 'asc'], Query(description='ソート順序 (desc: 新しい順, asc: 古い順)。')] = 'desc',
    page: Annotated[int, Query(description='ページ番号 (1始まり)。', ge=1)] = 1,
    search: Annotated[str | None, Query(description='番組名・ファイル名・チャンネル名での部分一致検索キーワード。')] = None,
):
    """
    サーバーに保存されたキャプチャ画像の一覧を取得する。<br>
    保存先フォルダ内の JPEG / PNG ファイルをスキャンし、ファイルの更新日時順にソートして返す。<br>
    search パラメータを指定すると、ファイル名・EXIF メタデータの番組名・チャンネル名のいずれかで部分一致検索する。<br>
    チャンネル名での検索は Channel テーブルから network_id/service_id を解決するため非同期関数にしている。
    """

    # すべての保存先フォルダからキャプチャ画像ファイルを収集する
    capture_files = CollectCaptureFiles()

    # 検索語に一致するチャンネルの network_id/service_id ペアを事前に収集する
    # これにより、チャンネル名での検索もファイル名・番組名検索と同様に動作する
    search_channel_nid_sid_pairs: set[tuple[int, int]] = set()
    if search is not None:
        matching_channels = await Channel.filter(name__icontains=search).all()
        for ch in matching_channels:
            search_channel_nid_sid_pairs.add((ch.network_id, ch.service_id))

    # 検索が指定されている場合、フィルタリングを行う
    if search is not None:
        search_lower = search.lower()
        filtered_files: list[tuple[str, float, Path]] = []

        for filename, mtime, filepath in capture_files:
            # Step 1: ファイル名での部分一致検索 (軽い処理)
            if search_lower in filename.lower():
                filtered_files.append((filename, mtime, filepath))
                continue

            # Step 2: ファイル名でマッチしなかった場合は EXIF メタデータを読み取る
            metadata = ExtractCaptureMetadataOnly(filepath)
            if metadata is None:
                # メタデータがない場合はマッチしない
                continue

            # Step 2a: 番組名 (title) での部分一致検索
            if search_lower in metadata.title.lower():
                filtered_files.append((filename, mtime, filepath))
                continue

            # Step 2b: チャンネル名での検索 (検索語に一致するチャンネルの network_id/service_id と照合)
            if (metadata.network_id, metadata.service_id) in search_channel_nid_sid_pairs:
                filtered_files.append((filename, mtime, filepath))
                continue

        capture_files = filtered_files

    # ファイルの更新日時でソートする
    reverse = (order == 'desc')
    capture_files.sort(key=lambda x: x[1], reverse=reverse)

    # 総数を記録
    total = len(capture_files)

    # ページネーションを適用して現在のページのファイルのみを取得する
    offset = (page - 1) * PAGE_SIZE
    page_files = capture_files[offset:offset + PAGE_SIZE]

    # 現在のページのファイルからメタデータを抽出する
    ## EXIF の読み取りは重い処理なので、ページネーション適用後のファイルのみに対して行う
    captures: list[schemas.Capture] = []
    for filename, mtime, filepath in page_files:
        capture = ExtractCaptureInfo(filepath)
        captures.append(capture)

    return schemas.Captures(
        total = total,
        captures = captures,
    )


# ==================== キャプチャフォルダ CRUD API ====================

@router.get(
    '/folders',
    summary = 'キャプチャフォルダ一覧 API',
    response_model = schemas.CaptureFolders,
)
async def CaptureFolderListAPI(
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    ログインユーザーが作成したキャプチャフォルダの一覧を sort_order 順で取得する。<br>
    各フォルダには紐付けられたキャプチャの件数 (capture_count) が含まれる。
    """

    # ログインユーザーのフォルダを sort_order 順で取得
    folder_models = await CaptureFolder.filter(user=current_user).order_by('sort_order', 'id')

    # 各フォルダのキャプチャ数を動的に算出してスキーマに変換する
    folders: list[schemas.CaptureFolder] = []
    for folder_model in folder_models:
        bookmark_count = await CaptureBookmark.filter(folder=folder_model).count()
        folders.append(schemas.CaptureFolder(
            id = folder_model.id,
            name = folder_model.name,
            sort_order = folder_model.sort_order,
            capture_count = bookmark_count,
            created_at = folder_model.created_at,
            updated_at = folder_model.updated_at,
        ))

    return schemas.CaptureFolders(
        total = len(folders),
        folders = folders,
    )


@router.post(
    '/folders',
    summary = 'キャプチャフォルダ作成 API',
    response_model = schemas.CaptureFolder,
    status_code = status.HTTP_201_CREATED,
)
async def CaptureFolderCreateAPI(
    request: schemas.CaptureFolderCreateRequest,
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    新しいキャプチャフォルダを作成する。<br>
    sort_order は既存フォルダの最大値 + 1 に自動設定される。
    """

    # フォルダ名のバリデーション
    if not request.name.strip():
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Folder name cannot be empty',
        )

    # 既存フォルダの最大 sort_order を取得し、+1 した値を新しいフォルダの sort_order にする
    max_sort_order_folder = await CaptureFolder.filter(user=current_user).order_by('-sort_order').first()
    new_sort_order = (max_sort_order_folder.sort_order + 1) if max_sort_order_folder else 0

    # フォルダを作成
    folder_model = await CaptureFolder.create(
        user = current_user,
        name = request.name.strip(),
        sort_order = new_sort_order,
    )

    return schemas.CaptureFolder(
        id = folder_model.id,
        name = folder_model.name,
        sort_order = folder_model.sort_order,
        capture_count = 0,
        created_at = folder_model.created_at,
        updated_at = folder_model.updated_at,
    )


@router.put(
    '/folders/{folder_id}',
    summary = 'キャプチャフォルダ更新 API',
    response_model = schemas.CaptureFolder,
)
async def CaptureFolderUpdateAPI(
    folder_id: int,
    request: schemas.CaptureFolderUpdateRequest,
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    指定されたキャプチャフォルダの名前や表示順序を更新する。<br>
    他のユーザーのフォルダにはアクセスできない。
    """

    # ログインユーザーのフォルダを取得 (他ユーザーのフォルダは 404 で拒否)
    folder_model = await CaptureFolder.filter(id=folder_id, user=current_user).first()
    if folder_model is None:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = 'Capture folder not found',
        )

    # 指定されたフィールドのみ更新する
    if request.name is not None:
        if not request.name.strip():
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail = 'Folder name cannot be empty',
            )
        folder_model.name = request.name.strip()
    if request.sort_order is not None:
        folder_model.sort_order = request.sort_order

    await folder_model.save()

    # キャプチャ数を算出
    bookmark_count = await CaptureBookmark.filter(folder=folder_model).count()

    return schemas.CaptureFolder(
        id = folder_model.id,
        name = folder_model.name,
        sort_order = folder_model.sort_order,
        capture_count = bookmark_count,
        created_at = folder_model.created_at,
        updated_at = folder_model.updated_at,
    )


@router.delete(
    '/folders/{folder_id}',
    summary = 'キャプチャフォルダ削除 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def CaptureFolderDeleteAPI(
    folder_id: int,
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    指定されたキャプチャフォルダを削除する。<br>
    CASCADE 設定により、フォルダに紐付けられた CaptureBookmark レコードも自動削除される。<br>
    実際のキャプチャ画像ファイルは削除されない。
    """

    # ログインユーザーのフォルダを取得 (他ユーザーのフォルダは 404 で拒否)
    folder_model = await CaptureFolder.filter(id=folder_id, user=current_user).first()
    if folder_model is None:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = 'Capture folder not found',
        )

    await folder_model.delete()


# ==================== フォルダ内キャプチャ操作 API ====================

@router.get(
    '/folders/{folder_id}/captures',
    summary = 'フォルダ内キャプチャ一覧 API',
    response_model = schemas.Captures,
)
async def CaptureFolderCaptureListAPI(
    folder_id: int,
    current_user: Annotated[User, Depends(GetCurrentUser)],
    order: Annotated[Literal['desc', 'asc'], Query(description='ソート順序 (desc: 新しい順, asc: 古い順)。')] = 'desc',
    page: Annotated[int, Query(description='ページ番号 (1始まり)。', ge=1)] = 1,
):
    """
    指定されたフォルダに紐付けられたキャプチャの一覧を取得する。<br>
    CaptureBookmark からファイル名リストを取得し、実ファイルの存在を確認したうえで
    ExtractCaptureInfo() でメタデータを抽出して返す。<br>
    フォルダに紐付けられているが実ファイルが存在しないブックマークはレスポンスから除外する。
    """

    # ログインユーザーのフォルダを取得
    folder_model = await CaptureFolder.filter(id=folder_id, user=current_user).first()
    if folder_model is None:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = 'Capture folder not found',
        )

    # フォルダに紐付けられたブックマークのファイル名一覧を取得
    bookmarks = await CaptureBookmark.filter(folder=folder_model).all()

    # 各ブックマークについて実ファイルの存在を確認し、有効なキャプチャのみを収集する
    capture_files: list[tuple[str, float, Path]] = []
    for bookmark in bookmarks:
        filepath = FindCaptureFile(bookmark.filename)
        if filepath is not None:
            stat = filepath.stat()
            capture_files.append((bookmark.filename, stat.st_mtime, filepath))

    # ファイルの更新日時でソートする
    reverse = (order == 'desc')
    capture_files.sort(key=lambda x: x[1], reverse=reverse)

    # 総数を記録
    total = len(capture_files)

    # ページネーションを適用
    offset = (page - 1) * PAGE_SIZE
    page_files = capture_files[offset:offset + PAGE_SIZE]

    # メタデータを抽出する
    captures: list[schemas.Capture] = []
    for _, _, filepath in page_files:
        capture = ExtractCaptureInfo(filepath)
        captures.append(capture)

    return schemas.Captures(
        total = total,
        captures = captures,
    )


@router.post(
    '/folders/{folder_id}/captures',
    summary = 'フォルダへキャプチャ追加 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def CaptureFolderCaptureAddAPI(
    folder_id: int,
    request: schemas.CaptureBookmarkRequest,
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    指定されたフォルダにキャプチャを一括追加する。<br>
    request.filenames に含まれる各ファイル名について、実ファイルの存在を確認し、
    CaptureBookmark レコードを作成する。既に紐付け済みのファイルは無視される。
    """

    # ログインユーザーのフォルダを取得
    folder_model = await CaptureFolder.filter(id=folder_id, user=current_user).first()
    if folder_model is None:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = 'Capture folder not found',
        )

    # 各ファイル名についてブックマークを作成する
    for filename in request.filenames:
        # 実ファイルの存在を確認
        filepath = FindCaptureFile(filename)
        if filepath is None:
            logging.warning(f'[CapturesRouter][CaptureFolderCaptureAddAPI] Capture file not found, skipping: {filename}')
            continue

        # 既に同じフォルダに同じファイル名が登録されていないか確認 (unique_together 制約の事前チェック)
        existing = await CaptureBookmark.filter(folder=folder_model, filename=filename).exists()
        if existing:
            continue

        # ブックマークを作成
        await CaptureBookmark.create(
            folder = folder_model,
            filename = filename,
        )


@router.delete(
    '/folders/{folder_id}/captures',
    summary = 'フォルダからキャプチャ削除 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def CaptureFolderCaptureRemoveAPI(
    folder_id: int,
    request: schemas.CaptureBookmarkRequest,
    current_user: Annotated[User, Depends(GetCurrentUser)],
):
    """
    指定されたフォルダからキャプチャを一括削除する。<br>
    CaptureBookmark レコードを削除するだけで、実際のキャプチャ画像ファイルは削除しない。
    """

    # ログインユーザーのフォルダを取得
    folder_model = await CaptureFolder.filter(id=folder_id, user=current_user).first()
    if folder_model is None:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = 'Capture folder not found',
        )

    # 指定されたファイル名のブックマークを一括削除
    await CaptureBookmark.filter(folder=folder_model, filename__in=request.filenames).delete()


# ==================== キャプチャ画像取得・削除・アップロード API ====================

@router.get(
    '/{filename}',
    summary = 'キャプチャ画像取得 API',
    response_class = Response,
)
def CaptureImageAPI(
    filename: str,
    thumbnail: Annotated[bool, Query(description='サムネイル画像を返すかどうか。')] = False,
):
    """
    指定されたファイル名のキャプチャ画像を返す。<br>
    thumbnail=true を指定すると、サムネイル用に縮小した JPEG 画像を返す。<br>
    同期ファイル I/O を伴うため敢えて同期関数として実装している。
    """

    # キャプチャ画像を検索する
    filepath = FindCaptureFile(filename)
    if filepath is None:
        logging.error(f'[CapturesRouter][CaptureImageAPI] Capture file not found: {filename}')
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = 'Capture file not found',
        )

    # サムネイル画像が要求された場合は、Pillow でリサイズして返す
    if thumbnail:
        try:
            with Image.open(filepath) as img:
                # EXIF の回転情報を適用する
                transposed = ImageOps.exif_transpose(img)
                if transposed is not None:
                    img = transposed
                # 長辺を THUMBNAIL_MAX_SIZE に縮小する
                img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE), Image.Resampling.LANCZOS)
                # JPEG としてバイトデータに変換する
                buffer = io.BytesIO()
                # PNG の場合は RGBA モードの可能性があるため RGB に変換する
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                img.save(buffer, format='JPEG', quality=80)
                buffer.seek(0)
                return Response(
                    content = buffer.getvalue(),
                    media_type = 'image/jpeg',
                    headers = {
                        'Cache-Control': 'public, max-age=86400',
                    },
                )
        except Exception as ex:
            logging.error(f'[CapturesRouter][CaptureImageAPI] Failed to generate thumbnail for {filename}: {ex}')
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail = 'Failed to generate thumbnail',
            )

    # 元の画像をそのまま返す
    suffix = filepath.suffix.lower()
    if suffix in ('.jpg', '.jpeg'):
        media_type = 'image/jpeg'
    else:
        media_type = 'image/png'

    try:
        content = filepath.read_bytes()
    except OSError as ex:
        logging.error(f'[CapturesRouter][CaptureImageAPI] Failed to read capture file {filename}: {ex}')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Failed to read capture file',
        )

    return Response(
        content = content,
        media_type = media_type,
        headers = {
            'Cache-Control': 'public, max-age=86400',
        },
    )


@router.delete(
    '/{filename}',
    summary = 'キャプチャ画像削除 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
def CaptureDeleteAPI(
    filename: str,
):
    """
    指定されたファイル名のキャプチャ画像を削除する。<br>
    同期ファイル I/O を伴うため敢えて同期関数として実装している。
    """

    # キャプチャ画像を検索する
    filepath = FindCaptureFile(filename)
    if filepath is None:
        logging.error(f'[CapturesRouter][CaptureDeleteAPI] Capture file not found: {filename}')
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = 'Capture file not found',
        )

    # ファイルを削除する
    try:
        filepath.unlink()
    except PermissionError:
        logging.error(f'[CapturesRouter][CaptureDeleteAPI] Permission denied to delete the file: {filename}')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Permission denied to delete the file',
        )
    except OSError as ex:
        logging.error(f'[CapturesRouter][CaptureDeleteAPI] Failed to delete the file {filename}: {ex}')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Unexpected error occurred while deleting the file',
        )


@router.post(
    '',
    summary = 'キャプチャ画像アップロード API',
    status_code = status.HTTP_204_NO_CONTENT,
)
def CaptureUploadAPI(
    image: Annotated[UploadFile, File(description='アップロードするキャプチャ画像 (JPEG or PNG)。')],
):
    """
    クライアント側でキャプチャした画像をサーバーにアップロードする。<br>
    アップロードされた画像は、サーバー設定で指定されたフォルダに保存される。<br>
    同期ファイル I/O を伴うため敢えて同期関数として実装している。
    """

    # 画像が JPEG または PNG かをチェック
    ## 万が一悪意ある攻撃者から危険なファイルを送り込まれないように
    mimetype: str = puremagic.magic_stream(image.file)[0].mime_type
    if mimetype != 'image/jpeg' and mimetype != 'image/png':
        logging.error('[CapturesRouter][CaptureUploadAPI] Invalid image file was uploaded.')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Please upload JPEG or PNG image',
        )

    # シークを元に戻す（重要）
    ## puremagic を使った時点でファイルはシークされているため、戻さないと 0 バイトになる
    image.file.seek(0)

    # 先頭から順に保存容量が空いている保存先フォルダを探す
    upload_folders: list[Path] = [Path(folder) for folder in Config().capture.upload_folders]
    for index, upload_folder in enumerate(upload_folders):

        # 万が一保存先フォルダが存在しない場合は次の保存先フォルダを探す
        if not upload_folder.exists():
            continue

        # 保存先フォルダの空き容量が 10MB 未満なら、最後のフォルダでなければ次の保存先フォルダを探す
        upload_folder_disk_usage = shutil.disk_usage(upload_folder)
        if upload_folder_disk_usage.free < 10 * 1024 * 1024 and index < len(upload_folders) - 1:
            continue

        # ディレクトリトラバーサル対策のためのチェック
        ## ref: https://stackoverflow.com/a/45190125/17124142
        filename = Path(cast(str, image.filename))
        try:
            upload_folder.joinpath(filename).resolve().relative_to(upload_folder.resolve())
        except ValueError:
            logging.error('[CapturesRouter][CaptureUploadAPI] Invalid filename was specified.')
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail = 'Specified filename is invalid',
            )

        # 保存するファイルパス
        filepath = upload_folder / filename

        # 既にファイルが存在していた場合は上書きしないようにリネーム
        ## ref: https://note.nkmk.me/python-pathlib-name-suffix-parent/
        count = 1
        while filepath.exists():
            filepath = upload_folder / f'{filename.stem}-{count}{filename.suffix}'
            count += 1

        # キャプチャを保存
        try:
            with open(filepath, mode='wb') as buffer:
                shutil.copyfileobj(image.file, buffer)
        except PermissionError:
            logging.error('[CapturesRouter][CaptureUploadAPI] Permission denied to save the file.')
            raise HTTPException(
                status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail = 'Permission denied to save the file',
            )
        except OSError as ex:
            is_disk_full_error = False
            if hasattr(ex, 'winerror'):
                is_disk_full_error = ex.winerror == 112  # type: ignore
            if hasattr(ex, 'errno'):
                is_disk_full_error = ex.errno == errno.ENOSPC
            if is_disk_full_error is True:
                logging.error('[CapturesRouter][CaptureUploadAPI] No space left on the device.')
                raise HTTPException(
                    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail = 'No space left on the device',
                )
            else:
                logging.error('[CapturesRouter][CaptureUploadAPI] Unexpected OSError:', exc_info=ex)
                raise HTTPException(
                    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail = 'Unexpected error occurred while saving the file',
                )

        # キャプチャのアップロードに成功したら 204 No Content を返す
        return

    # 保存先フォルダが見つからなかった場合はエラー
    logging.error('[CapturesRouter][CaptureUploadAPI] No available folder to save the file.')
    raise HTTPException(
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail = 'No available folder to save the file',
    )
