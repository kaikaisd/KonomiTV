
import asyncio
import copy
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from app import logging, schemas
from app.config import Config
from app.encoding.EncodingQueueManager import EncodingQueueManager
from app.models.EncodingTask import EncodingTask
from app.models.RecordedVideo import RecordedVideo


# ルーター
router = APIRouter(
    tags = ['Encoding Tasks'],
    prefix = '/api/encoding-tasks',
)


def _taskToResponse(task: EncodingTask) -> schemas.EncodingTaskResponse:
    """
    EncodingTask モデルを EncodingTaskResponse スキーマに変換するヘルパー関数。

    Args:
        task (EncodingTask): DB から取得したエンコードタスク

    Returns:
        schemas.EncodingTaskResponse: API レスポンス用スキーマ
    """
    return schemas.EncodingTaskResponse(
        id=task.id,
        source_file_path=task.source_file_path,
        output_file_path=task.output_file_path,
        recorded_video_id=task.recorded_video_id,
        encoder_type=task.encoder_type,
        video_codec=task.video_codec,
        quality_preset=task.quality_preset,
        video_bitrate=task.video_bitrate,
        audio_bitrate=task.audio_bitrate,
        cm_removal=task.cm_removal,
        status=task.status,
        priority=task.priority,
        progress=task.progress,
        fail_reason=task.fail_reason,
        added_at=task.added_at,
        encoding_started_at=task.encoding_started_at,
        encoding_finished_at=task.encoding_finished_at,
    )


@router.get(
    '',
    summary = 'エンコードタスク一覧 API',
    response_description = 'エンコードタスクの一覧。',
    response_model = schemas.EncodingTaskListResponse,
)
async def EncodingTasksAPI(
    task_status: Annotated[schemas.EncodingTaskStatusType | None, Query(alias='status', description='ステータスでフィルタ')] = None,
    recorded_video_id: Annotated[int | None, Query(description='RecordedVideo ID でフィルタ (サブ ID リンク用)')] = None,
    page: Annotated[int, Query(ge=1, description='ページ番号')] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description='1ページあたりの件数')] = 50,
):
    """
    すべてのエンコードタスクの一覧を取得する。<br>
    ステータス・RecordedVideo ID でのフィルタリングとページネーションをサポートする。
    """

    # クエリの組み立て
    query = EncodingTask.all()
    if task_status is not None:
        query = query.filter(status=task_status)
    # recorded_video_id でフィルタ (特定の録画番組に紐づくエンコードタスクを取得する際に使用)
    if recorded_video_id is not None:
        query = query.filter(recorded_video_id=recorded_video_id)

    # 合計件数を取得
    total = await query.count()

    # ページネーションを適用して取得 (優先度降順 → 追加日時降順)
    offset = (page - 1) * per_page
    tasks = await query.order_by('-priority', '-added_at').offset(offset).limit(per_page)

    return schemas.EncodingTaskListResponse(
        total=total,
        encoding_tasks=[_taskToResponse(task) for task in tasks],
    )


@router.post(
    '',
    summary = 'エンコードタスク追加 API',
    response_description = '追加されたエンコードタスク。',
    response_model = schemas.EncodingTaskResponse,
    status_code = status.HTTP_201_CREATED,
)
async def EncodingTaskAddAPI(request: schemas.EncodingTaskAddRequest):
    """
    新しいエンコードタスクをキューに追加する。<br>
    RecordedVideo の ID を指定して、その録画番組をバッチエンコードする。
    """

    # RecordedVideo の存在確認
    recorded_video = await RecordedVideo.get_or_none(id=request.recorded_video_id)
    if recorded_video is None:
        logging.error(f'[EncodingTasksRouter][EncodingTaskAddAPI] RecordedVideo not found. [id: {request.recorded_video_id}]')
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Specified recorded_video_id was not found.',
        )

    # エンコードプロファイルから設定値を解決する
    # profile_name が指定された場合はそのプロファイルを使用し、
    # 省略時はサーバー設定のデフォルトプロファイルを使用する
    encoding_config = Config().encoding
    profile_name = request.profile_name or encoding_config.default_profile_name
    profile = None
    for p in encoding_config.profiles:
        if p.name == profile_name:
            profile = p
            break
    # プロファイルが見つからない場合は最初のプロファイルにフォールバック
    if profile is None and len(encoding_config.profiles) > 0:
        profile = encoding_config.profiles[0]

    # プロファイルの設定値をベースに、リクエストで個別に指定された値で上書きする
    encoder_type = request.encoder_type or (profile.encoder_type if profile else 'FFmpeg')
    video_codec = request.video_codec or (profile.video_codec if profile else 'H.264')
    quality_preset = request.quality_preset or (profile.quality_preset if profile else 'medium')
    video_bitrate = request.video_bitrate or (profile.video_bitrate if profile else '4000k')
    audio_bitrate = request.audio_bitrate or (profile.audio_bitrate if profile else '192k')
    cm_removal = request.cm_removal if request.cm_removal is not None else (profile.cm_removal if profile else False)

    # エンコードタスクを作成
    task = await EncodingTask.create(
        source_file_path=recorded_video.file_path,
        recorded_video_id=recorded_video.id,
        encoder_type=encoder_type,
        video_codec=video_codec,
        quality_preset=quality_preset,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
        cm_removal=cm_removal,
        priority=request.priority,
        status='Pending',
    )

    logging.info(f'[EncodingTasksRouter][EncodingTaskAddAPI] Encoding task added. [task_id: {task.id}, source: {task.source_file_path}]')
    return _taskToResponse(task)


@router.get(
    '/events',
    summary = 'エンコードタスク イベント API',
    response_class = Response,
    responses = {
        status.HTTP_200_OK: {
            'description': 'エンコードタスクの状態変更イベントが随時配信されるイベントストリーム。',
            'content': {'text/event-stream': {}},
        }
    }
)
async def EncodingTasksEventAPI():
    """
    エンコードタスクの状態変更を Server-Sent Events で随時配信する。<br>
    イベントには initial_update (初回接続時の全タスクリスト) と tasks_update (変更検知時のタスクリスト) の2種類がある。
    """

    async def generator():
        """イベントストリームを出力するジェネレーター"""

        # 初回のタスク一覧を取得
        tasks = await EncodingTask.all().order_by('-priority', '-added_at')
        previous_data = schemas.EncodingTaskListResponse(
            total=len(tasks),
            encoding_tasks=[_taskToResponse(t) for t in tasks],
        )

        # 初回接続時に現在のタスク一覧を返す
        yield {
            'event': 'initial_update',
            'data': previous_data.model_dump_json(),
        }

        while True:
            # 現在のタスク一覧を取得
            tasks = await EncodingTask.all().order_by('-priority', '-added_at')
            current_data = schemas.EncodingTaskListResponse(
                total=len(tasks),
                encoding_tasks=[_taskToResponse(t) for t in tasks],
            )

            # 前回と異なる場合のみイベントを送信
            if previous_data != current_data:
                yield {
                    'event': 'tasks_update',
                    'data': current_data.model_dump_json(),
                }
                previous_data = copy.deepcopy(current_data)

            # ポーリング間隔
            await asyncio.sleep(0.5)

    return EventSourceResponse(generator())


@router.get(
    '/{task_id}',
    summary = 'エンコードタスク API',
    response_description = 'エンコードタスクの状態。',
    response_model = schemas.EncodingTaskResponse,
)
async def EncodingTaskAPI(
    task_id: Annotated[int, Path(description='エンコードタスク ID')],
):
    """
    指定されたエンコードタスクの状態を取得する。
    """

    task = await EncodingTask.get_or_none(id=task_id)
    if task is None:
        logging.error(f'[EncodingTasksRouter][EncodingTaskAPI] Task not found. [task_id: {task_id}]')
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Specified task_id was not found.',
        )

    return _taskToResponse(task)


@router.get(
    '/{task_id}/download',
    summary = 'エンコード済みファイルダウンロード API',
    response_class = Response,
    responses = {
        status.HTTP_200_OK: {
            'description': 'エンコード済みファイルのバイナリデータ。',
            'content': {'application/octet-stream': {}},
        }
    },
)
async def EncodingTaskDownloadAPI(
    task_id: Annotated[int, Path(description='エンコードタスク ID')],
):
    """
    完了済みのエンコードタスクの出力ファイルをダウンロードする。<br>
    サブ ID リンク: エンコード済みファイルと元の録画番組を紐付けてダウンロード可能にする。
    """
    from pathlib import Path as FilePath

    from fastapi.responses import FileResponse

    task = await EncodingTask.get_or_none(id=task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Specified task_id was not found.',
        )

    # 完了済みタスクのみダウンロード可能
    if task.status != 'Completed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Only completed encoding tasks can be downloaded.',
        )

    # 出力ファイルの存在確認
    output_path = FilePath(task.output_file_path)
    if not output_path.exists():
        logging.error(f'[EncodingTasksRouter][EncodingTaskDownloadAPI] Output file not found. [path: {task.output_file_path}]')
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Encoded output file not found on disk.',
        )

    logging.info(f'[EncodingTasksRouter][EncodingTaskDownloadAPI] Downloading encoded file. [task_id: {task_id}, path: {task.output_file_path}]')
    return FileResponse(
        path=output_path,
        filename=output_path.name,
        media_type='video/mp4',
    )


@router.put(
    '/{task_id}',
    summary = 'エンコードタスク更新 API',
    response_description = '更新されたエンコードタスク。',
    response_model = schemas.EncodingTaskResponse,
)
async def EncodingTaskUpdateAPI(
    task_id: Annotated[int, Path(description='エンコードタスク ID')],
    request: schemas.EncodingTaskUpdateRequest,
):
    """
    エンコードタスクの優先度変更またはキャンセルを行う。<br>
    ステータスの変更は Cancelled への変更のみ許可される。
    """

    task = await EncodingTask.get_or_none(id=task_id)
    if task is None:
        logging.error(f'[EncodingTasksRouter][EncodingTaskUpdateAPI] Task not found. [task_id: {task_id}]')
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Specified task_id was not found.',
        )

    # 優先度の更新
    if request.priority is not None:
        if task.status not in ('Pending',):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Priority can only be changed for Pending tasks.',
            )
        task.priority = request.priority
        await task.save()
        logging.info(f'[EncodingTasksRouter][EncodingTaskUpdateAPI] Priority updated. [task_id: {task_id}, priority: {request.priority}]')

    # キャンセル
    if request.status == 'Cancelled':
        if task.status not in ('Pending', 'Encoding'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Only Pending or Encoding tasks can be cancelled.',
            )
        success = await EncodingQueueManager.cancelTask(task_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to cancel encoding task.',
            )
        # DB を再取得して最新状態を返す
        task = await EncodingTask.get(id=task_id)

    return _taskToResponse(task)


@router.delete(
    '/{task_id}',
    summary = 'エンコードタスク削除 API',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def EncodingTaskDeleteAPI(
    task_id: Annotated[int, Path(description='エンコードタスク ID')],
):
    """
    完了・失敗・キャンセル済みのエンコードタスクを削除する。<br>
    Pending または Encoding 中のタスクは削除できない。
    """

    task = await EncodingTask.get_or_none(id=task_id)
    if task is None:
        logging.error(f'[EncodingTasksRouter][EncodingTaskDeleteAPI] Task not found. [task_id: {task_id}]')
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Specified task_id was not found.',
        )

    if task.status in ('Pending', 'Encoding'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Cannot delete Pending or Encoding tasks. Cancel them first.',
        )

    await task.delete()
    logging.info(f'[EncodingTasksRouter][EncodingTaskDeleteAPI] Task deleted. [task_id: {task_id}]')


@router.post(
    '/{task_id}/retry',
    summary = 'エンコードタスクリトライ API',
    response_description = 'リトライされたエンコードタスク。',
    response_model = schemas.EncodingTaskResponse,
)
async def EncodingTaskRetryAPI(
    task_id: Annotated[int, Path(description='エンコードタスク ID')],
):
    """
    失敗したエンコードタスクをリトライする。<br>
    ステータスを Pending にリセットし、エラー情報をクリアしてキューに戻す。
    """

    task = await EncodingTask.get_or_none(id=task_id)
    if task is None:
        logging.error(f'[EncodingTasksRouter][EncodingTaskRetryAPI] Task not found. [task_id: {task_id}]')
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Specified task_id was not found.',
        )

    if task.status not in ('Failed', 'Cancelled'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Only Failed or Cancelled tasks can be retried.',
        )

    # ステータスをリセット
    task.status = 'Pending'
    task.progress = 0.0
    task.fail_reason = ''
    task.output_file_path = ''
    task.encoding_started_at = None
    task.encoding_finished_at = None
    await task.save()

    logging.info(f'[EncodingTasksRouter][EncodingTaskRetryAPI] Task retried. [task_id: {task_id}]')
    return _taskToResponse(task)
