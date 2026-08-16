
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from tortoise.expressions import Q
from tortoise.functions import Count
from tortoise.queryset import Prefetch

from app import logging, schemas
from app.metadata.SeriesIndexer import ParseSeriesTitle
from app.models.RecordedProgram import RecordedProgram
from app.models.Series import Series
from app.models.SeriesBroadcastPeriod import SeriesBroadcastPeriod


# ルーター
router = APIRouter(
    tags = ['Series'],
    prefix = '/api/series',
)

# ページングで一度に取得するシリーズ番組の数
PAGE_SIZE = 30


def __buildSeriesQuerySet():
    """
    シリーズ取得用の共通クエリセットを構築する

    Series → broadcast_periods (リバースリレーション) → recorded_programs (リバースリレーション) の
    ネストされたリレーションを正しく prefetch するため、Prefetch オブジェクトを使用する。
    recorded_programs の直接 FK である recorded_video と channel は select_related で取得する。
    また、録画番組が2件以上紐づいているシリーズのみを返す (1件しかない番組はシリーズとして表示する意味がないため除外する) 。
    """
    return Series.all() \
        .annotate(recorded_program_count=Count('broadcast_periods__recorded_programs')) \
        .filter(recorded_program_count__gte=2) \
        .prefetch_related(
            Prefetch(
                'broadcast_periods',
                queryset=SeriesBroadcastPeriod.all().select_related('channel').prefetch_related(
                    Prefetch(
                        'recorded_programs',
                        queryset=RecordedProgram.all().select_related('recorded_video', 'channel'),
                    ),
                ),
            ),
        )


def __buildSeriesQuerySetUnfiltered():
    """
    フィルターなしのシリーズ取得用クエリセットを構築する

    __buildSeriesQuerySet() と同じ prefetch 構造だが、recorded_program_count >= 2 のフィルターを適用しない。
    新規作成した (0-1件の) シリーズや、番組追加直後のシリーズを返す場合に使用する。
    """
    return Series.all() \
        .prefetch_related(
            Prefetch(
                'broadcast_periods',
                queryset=SeriesBroadcastPeriod.all().select_related('channel').prefetch_related(
                    Prefetch(
                        'recorded_programs',
                        queryset=RecordedProgram.all().select_related('recorded_video', 'channel'),
                    ),
                ),
            ),
        )


@router.get(
    '',
    summary = 'シリーズ番組一覧 API',
    response_description = 'シリーズ番組のリスト。',
    response_model = schemas.SeriesList,
)
async def SeriesListAPI(
    order: Annotated[Literal['desc', 'asc'], Query(description='ソート順序 (desc or asc) 。')] = 'desc',
    page: Annotated[int, Query(description='ページ番号。')] = 1,
):
    """
    すべてのシリーズ番組を一度に 30 件ずつ取得する。<br>
    order には "desc" か "asc" を指定する。<br>
    page (ページ番号) には 1 以上の整数を指定する。
    """

    series_list = await __buildSeriesQuerySet() \
        .order_by('-updated_at' if order == 'desc' else 'updated_at') \
        .offset((page - 1) * PAGE_SIZE) \
        .limit(PAGE_SIZE)

    # 2件以上の録画番組を持つシリーズのみカウントする
    total = await Series.all() \
        .annotate(recorded_program_count=Count('broadcast_periods__recorded_programs')) \
        .filter(recorded_program_count__gte=2) \
        .count()

    return {
        'total': total,
        'series_list': series_list,
    }


@router.get(
    '/search',
    summary = 'シリーズ番組検索 API',
    response_description = '検索条件に一致するシリーズ番組のリスト。',
    response_model = schemas.SeriesList,
)
async def SeriesSearchAPI(
    query: Annotated[str, Query(description='検索キーワード。title または description のいずれかに部分一致するシリーズ番組を検索する。')] = '',
    order: Annotated[Literal['desc', 'asc'], Query(description='ソート順序 (desc or asc) 。')] = 'desc',
    page: Annotated[int, Query(description='ページ番号。')] = 1,
):
    """
    指定されたキーワードでシリーズ番組を一度に 30 件ずつ検索する。<br>
    キーワードは title または description のいずれかに部分一致するシリーズ番組を検索する。<br>
    order には "desc" か "asc" を指定する。<br>
    page (ページ番号) には 1 以上の整数を指定する。
    """

    # クエリが空の場合は全件取得と同じ挙動にする
    if not query:
        return await SeriesListAPI(order=order, page=page)

    # 検索条件を構築
    # title または description のいずれかに部分一致するレコードを検索
    search_filter = Q(title__icontains=query) | Q(description__icontains=query)

    series_list = await __buildSeriesQuerySet() \
        .filter(search_filter) \
        .order_by('-updated_at' if order == 'desc' else 'updated_at') \
        .offset((page - 1) * PAGE_SIZE) \
        .limit(PAGE_SIZE)

    # 検索条件に一致し、かつ2件以上の録画番組を持つシリーズの総件数を取得
    total = await Series.all() \
        .annotate(recorded_program_count=Count('broadcast_periods__recorded_programs')) \
        .filter(recorded_program_count__gte=2) \
        .filter(search_filter) \
        .count()

    return {
        'total': total,
        'series_list': series_list,
    }


@router.get(
    '/{series_id}',
    summary = 'シリーズ番組 API',
    response_description = 'シリーズ番組。',
    response_model = schemas.Series,
)
async def SeriesAPI(
    series_id: Annotated[int, Path(description='シリーズ番組の ID 。')],
):
    """
    指定されたシリーズ番組を取得する。
    """

    # フィルターなしのクエリセットを使用し、1件以下の番組しかないシリーズも取得可能にする
    series = await __buildSeriesQuerySetUnfiltered() \
        .get_or_none(id=series_id)
    if series is None:
        logging.warning(f'[SeriesRouter][SeriesAPI] Specified series_id was not found. [series_id: {series_id}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Specified series_id was not found',
        )

    return series


@router.put(
    '/{series_id}',
    summary = 'シリーズ番組更新 API',
    response_description = '更新後のシリーズ番組。',
    response_model = schemas.Series,
)
async def SeriesUpdateAPI(
    series_id: Annotated[int, Path(description='シリーズ番組の ID 。')],
    request: schemas.SeriesUpdateRequest,
):
    """
    指定されたシリーズ番組のタイトルを変更する。<br>
    変更後、シリーズに紐づく全録画番組の series_title も更新し、手動編集済みフラグを立てる。
    """

    # シリーズを取得
    series = await Series.get_or_none(id=series_id)
    if series is None:
        logging.warning(f'[SeriesRouter][SeriesUpdateAPI] Specified series_id was not found. [series_id: {series_id}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Specified series_id was not found',
        )

    # シリーズタイトルを更新
    series.title = request.title
    await series.save()

    # シリーズに紐づく全 RecordedProgram の series_title を更新し、手動編集済みフラグを立てる
    # SeriesBroadcastPeriod 経由で紐づく全録画番組を対象にする
    period_ids = await SeriesBroadcastPeriod.filter(series_id=series_id).values_list('id', flat=True)
    await RecordedProgram.filter(series_broadcast_period_id__in=period_ids).update(
        series_title=request.title,
        is_series_manually_edited=True,
    )

    logging.info(f'[SeriesRouter][SeriesUpdateAPI] Series title updated. [series_id: {series_id}, new_title: {request.title}]')

    # 更新後のシリーズを prefetch 込みで返す (フィルターなし版を使用)
    updated_series = await __buildSeriesQuerySetUnfiltered() \
        .get_or_none(id=series_id)
    if updated_series is None:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Series not found after update',
        )

    return updated_series


@router.delete(
    '/{series_id}/programs/{program_id}',
    summary = 'シリーズ番組除外 API',
    response_description = '除外成功。',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def SeriesRemoveProgramAPI(
    series_id: Annotated[int, Path(description='シリーズ番組の ID 。')],
    program_id: Annotated[int, Path(description='除外する録画番組の ID 。')],
):
    """
    指定された録画番組をシリーズから除外する。<br>
    除外後、その録画番組は手動編集済みフラグが立てられ、自動再割り当ての対象外になる。<br>
    除外の結果シリーズ内の録画番組が0件になった場合、シリーズ自体も削除される。
    """

    # 対象の録画番組を取得 (指定されたシリーズに紐づいていることを確認)
    program = await RecordedProgram.get_or_none(id=program_id, series_id=series_id)
    if program is None:
        logging.warning(
            f'[SeriesRouter][SeriesRemoveProgramAPI] Specified program was not found in the series. '
            f'[series_id: {series_id}, program_id: {program_id}]'
        )
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Specified program was not found in the series',
        )

    # 除外前に所属していた SeriesBroadcastPeriod の ID を記録
    old_period_id = program.series_broadcast_period_id

    # 録画番組のシリーズ紐付けを解除し、手動編集済みフラグを立てる
    program.series_id = None  # type: ignore
    program.series_broadcast_period_id = None  # type: ignore
    program.is_series_manually_edited = True
    await program.save()

    logging.info(
        f'[SeriesRouter][SeriesRemoveProgramAPI] Program removed from series. '
        f'[series_id: {series_id}, program_id: {program_id}]'
    )

    # 除外後、元の SeriesBroadcastPeriod に紐づく録画番組が0件になった場合は削除
    if old_period_id is not None:
        remaining_in_period = await RecordedProgram.filter(series_broadcast_period_id=old_period_id).count()
        if remaining_in_period == 0:
            await SeriesBroadcastPeriod.filter(id=old_period_id).delete()
            logging.info(
                f'[SeriesRouter][SeriesRemoveProgramAPI] Empty broadcast period deleted. '
                f'[period_id: {old_period_id}]'
            )

    # シリーズ全体で紐づく録画番組が0件になった場合はシリーズ自体を削除
    # SeriesBroadcastPeriod 経由で紐づく録画番組の総数を確認
    remaining_period_ids = await SeriesBroadcastPeriod.filter(series_id=series_id).values_list('id', flat=True)
    if len(remaining_period_ids) == 0:
        # 全ての放送期間が削除されている場合、シリーズも削除
        await Series.filter(id=series_id).delete()
        logging.info(
            f'[SeriesRouter][SeriesRemoveProgramAPI] Empty series deleted. [series_id: {series_id}]'
        )
    else:
        # まだ放送期間が残っている場合でも、全ての放送期間に紐づく録画番組が0件なら削除
        remaining_programs = await RecordedProgram.filter(series_broadcast_period_id__in=remaining_period_ids).count()
        if remaining_programs == 0:
            await SeriesBroadcastPeriod.filter(series_id=series_id).delete()
            await Series.filter(id=series_id).delete()
            logging.info(
                f'[SeriesRouter][SeriesRemoveProgramAPI] Empty series and periods deleted. [series_id: {series_id}]'
            )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    '',
    summary = 'シリーズ番組作成 API',
    response_description = '作成されたシリーズ番組。',
    response_model = schemas.Series,
    status_code = status.HTTP_201_CREATED,
)
async def SeriesCreateAPI(
    request: schemas.SeriesCreateRequest,
):
    """
    新しいシリーズを作成する。<br>
    タイトルのみを指定して空のシリーズを作成し、後から番組を追加する使い方を想定している。
    """

    # 空のシリーズを作成 (description と genres はデフォルト値)
    series = await Series.create(
        title=request.title,
        description='',
        genres=[],
    )

    logging.info(f'[SeriesRouter][SeriesCreateAPI] Series created. [series_id: {series.id}, title: {request.title}]')

    # 作成されたシリーズを prefetch 込みで返す (フィルターなし版を使用: 0件でも返す必要があるため)
    created_series = await __buildSeriesQuerySetUnfiltered() \
        .get_or_none(id=series.id)
    if created_series is None:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Series not found after creation',
        )

    return created_series


@router.delete(
    '/{series_id}',
    summary = 'シリーズ番組削除 API',
    response_description = '削除成功。',
    status_code = status.HTTP_204_NO_CONTENT,
)
async def SeriesDeleteAPI(
    series_id: Annotated[int, Path(description='シリーズ番組の ID 。')],
):
    """
    指定されたシリーズを削除する。<br>
    シリーズに紐づく全録画番組の紐付けを解除してから、シリーズ本体を削除する。<br>
    紐付け解除された録画番組には手動編集済みフラグが立てられ、自動再割り当ての対象外になる。
    """

    # シリーズを取得
    series = await Series.get_or_none(id=series_id)
    if series is None:
        logging.warning(f'[SeriesRouter][SeriesDeleteAPI] Specified series_id was not found. [series_id: {series_id}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Specified series_id was not found',
        )

    # シリーズに紐づく全 SeriesBroadcastPeriod の ID を取得
    period_ids = await SeriesBroadcastPeriod.filter(series_id=series_id).values_list('id', flat=True)

    # 重要: RecordedProgram の series FK は on_delete=CASCADE なので、
    # 先にプログラムの紐付けを解除してから Series を削除する必要がある
    # (そのまま削除すると RecordedProgram も消えてしまう)
    if len(period_ids) > 0:
        await RecordedProgram.filter(series_broadcast_period_id__in=period_ids).update(
            series_id=None,
            series_broadcast_period_id=None,
            is_series_manually_edited=True,
        )

    # SeriesBroadcastPeriod を削除してからシリーズ本体を削除
    await SeriesBroadcastPeriod.filter(series_id=series_id).delete()
    await Series.filter(id=series_id).delete()

    logging.info(f'[SeriesRouter][SeriesDeleteAPI] Series deleted. [series_id: {series_id}]')

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    '/{series_id}/programs/{program_id}',
    summary = 'シリーズ番組追加 API',
    response_description = '更新後のシリーズ番組。',
    response_model = schemas.Series,
)
async def SeriesAddProgramAPI(
    series_id: Annotated[int, Path(description='シリーズ番組の ID 。')],
    program_id: Annotated[int, Path(description='追加する録画番組の ID 。')],
):
    """
    指定された録画番組をシリーズに追加する。<br>
    追加された録画番組は手動編集済みフラグが立てられ、自動再割り当ての対象外になる。<br>
    番組がまだ episode_number や subtitle を持っていない場合、SeriesIndexer で解析して補完する。
    """

    # シリーズを取得
    series = await Series.get_or_none(id=series_id)
    if series is None:
        logging.warning(f'[SeriesRouter][SeriesAddProgramAPI] Specified series_id was not found. [series_id: {series_id}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Specified series_id was not found',
        )

    # 録画番組を取得 (channel も必要なので select_related で取得)
    program = await RecordedProgram.get_or_none(id=program_id).select_related('channel')
    if program is None:
        logging.warning(f'[SeriesRouter][SeriesAddProgramAPI] Specified program_id was not found. [program_id: {program_id}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Specified program_id was not found',
        )

    # 既にこのシリーズに所属している場合はエラー
    if program.series_id == series_id:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Program is already in this series',
        )

    # 別のシリーズに所属している場合は、まず元のシリーズから除外する
    if program.series_id is not None:
        old_series_id = program.series_id
        old_period_id = program.series_broadcast_period_id

        # 元のシリーズからの紐付けを解除
        program.series_id = None  # type: ignore
        program.series_broadcast_period_id = None  # type: ignore
        await program.save()

        # 元の SeriesBroadcastPeriod が空になった場合は削除
        if old_period_id is not None:
            remaining = await RecordedProgram.filter(series_broadcast_period_id=old_period_id).count()
            if remaining == 0:
                await SeriesBroadcastPeriod.filter(id=old_period_id).delete()

        # 元のシリーズが空になった場合は削除
        old_remaining_period_ids = await SeriesBroadcastPeriod.filter(series_id=old_series_id).values_list('id', flat=True)
        if len(old_remaining_period_ids) == 0:
            await Series.filter(id=old_series_id).delete()
            logging.info(f'[SeriesRouter][SeriesAddProgramAPI] Old empty series deleted. [old_series_id: {old_series_id}]')
        else:
            old_remaining_programs = await RecordedProgram.filter(series_broadcast_period_id__in=old_remaining_period_ids).count()
            if old_remaining_programs == 0:
                await SeriesBroadcastPeriod.filter(series_id=old_series_id).delete()
                await Series.filter(id=old_series_id).delete()
                logging.info(f'[SeriesRouter][SeriesAddProgramAPI] Old empty series and periods deleted. [old_series_id: {old_series_id}]')

    # 適切な SeriesBroadcastPeriod を find_or_create する
    # channel がある場合は同一 series_id + channel_id の期間を検索
    broadcast_period: SeriesBroadcastPeriod | None = None
    if program.channel_id is not None:
        broadcast_period = await SeriesBroadcastPeriod.get_or_none(
            series_id=series_id,
            channel_id=program.channel_id,
        )

    program_date = program.start_time.date() if program.start_time else date.today()

    if broadcast_period is not None:
        # 既存の放送期間の日付範囲を拡張する (番組の放送日が範囲外なら拡張)
        if program_date < broadcast_period.start_date:
            broadcast_period.start_date = program_date
        if program_date > broadcast_period.end_date:
            broadcast_period.end_date = program_date
        await broadcast_period.save()
    else:
        # 新しい放送期間を作成
        # channel がない場合は channel_id にフォールバック用の値を入れる必要がある
        channel_id = program.channel_id
        if channel_id is None:
            # channel が不明な場合、既存の期間があればそれを使う (channel を問わず最初の期間)
            existing_period = await SeriesBroadcastPeriod.filter(series_id=series_id).first()
            if existing_period is not None:
                # 日付範囲を拡張
                if program_date < existing_period.start_date:
                    existing_period.start_date = program_date
                if program_date > existing_period.end_date:
                    existing_period.end_date = program_date
                await existing_period.save()
                broadcast_period = existing_period
            else:
                # channel_id は NOT NULL なので、channel がない録画番組の場合はエラー
                raise HTTPException(
                    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail = 'Program has no channel and no existing broadcast period to assign to',
                )
        else:
            broadcast_period = await SeriesBroadcastPeriod.create(
                series_id=series_id,
                channel_id=channel_id,
                start_date=program_date,
                end_date=program_date,
            )

    # 録画番組をシリーズに紐付ける
    program.series_id = series_id  # type: ignore
    program.series_broadcast_period_id = broadcast_period.id  # type: ignore
    program.series_title = series.title
    program.is_series_manually_edited = True

    # episode_number や subtitle が未設定の場合、SeriesIndexer で解析して補完する
    ## ParseSeriesTitle() は確定的に解析できなかった場合に None を返すため、その場合は補完しない
    if program.episode_number is None or program.subtitle is None:
        parse_result = ParseSeriesTitle(program.title, program.genres, program.description)
        if parse_result is not None:
            if program.episode_number is None and parse_result.episode_number is not None:
                program.episode_number = parse_result.episode_number
            if program.subtitle is None and parse_result.subtitle is not None:
                program.subtitle = parse_result.subtitle

    await program.save()

    logging.info(
        f'[SeriesRouter][SeriesAddProgramAPI] Program added to series. '
        f'[series_id: {series_id}, program_id: {program_id}]'
    )

    # 更新後のシリーズを prefetch 込みで返す (フィルターなし版を使用)
    updated_series = await __buildSeriesQuerySetUnfiltered() \
        .get_or_none(id=series_id)
    if updated_series is None:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Series not found after adding program',
        )

    return updated_series


@router.post(
    '/{source_series_id}/merge/{target_series_id}',
    summary = 'シリーズマージ API',
    response_description = 'マージ後のターゲットシリーズ。',
    response_model = schemas.Series,
)
async def SeriesMergeAPI(
    source_series_id: Annotated[int, Path(description='マージ元シリーズの ID 。')],
    target_series_id: Annotated[int, Path(description='マージ先シリーズの ID 。')],
):
    """
    マージ元シリーズの全録画番組をマージ先シリーズに移動し、マージ元シリーズを削除する。<br>
    移動された録画番組には手動編集済みフラグが立てられ、自動再割り当ての対象外になる。
    """

    # 同一シリーズへのマージは不可
    if source_series_id == target_series_id:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Cannot merge a series into itself',
        )

    # マージ元シリーズを取得
    source_series = await Series.get_or_none(id=source_series_id)
    if source_series is None:
        logging.warning(f'[SeriesRouter][SeriesMergeAPI] Source series not found. [source_series_id: {source_series_id}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Source series not found',
        )

    # マージ先シリーズを取得
    target_series = await Series.get_or_none(id=target_series_id)
    if target_series is None:
        logging.warning(f'[SeriesRouter][SeriesMergeAPI] Target series not found. [target_series_id: {target_series_id}]')
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Target series not found',
        )

    # マージ元シリーズに紐づく全 SeriesBroadcastPeriod を取得
    source_period_ids = await SeriesBroadcastPeriod.filter(series_id=source_series_id).values_list('id', flat=True)

    # マージ元シリーズに紐づく全録画番組を取得
    source_programs = await RecordedProgram.filter(
        series_broadcast_period_id__in=source_period_ids,
    ).select_related('channel')

    # 各番組をマージ先シリーズに移動する
    for program in source_programs:
        # マージ先シリーズ内で同一 channel_id の SeriesBroadcastPeriod を検索
        target_period: SeriesBroadcastPeriod | None = None
        if program.channel_id is not None:
            target_period = await SeriesBroadcastPeriod.get_or_none(
                series_id=target_series_id,
                channel_id=program.channel_id,
            )

        program_date = program.start_time.date() if program.start_time else date.today()

        if target_period is not None:
            # 既存の放送期間の日付範囲を拡張する
            if program_date < target_period.start_date:
                target_period.start_date = program_date
            if program_date > target_period.end_date:
                target_period.end_date = program_date
            await target_period.save()
        else:
            # 新しい放送期間を作成
            channel_id = program.channel_id
            if channel_id is not None:
                target_period = await SeriesBroadcastPeriod.create(
                    series_id=target_series_id,
                    channel_id=channel_id,
                    start_date=program_date,
                    end_date=program_date,
                )
            else:
                # channel がない場合、マージ先の既存の期間を使う
                existing_period = await SeriesBroadcastPeriod.filter(series_id=target_series_id).first()
                if existing_period is not None:
                    target_period = existing_period
                    if program_date < target_period.start_date:
                        target_period.start_date = program_date
                    if program_date > target_period.end_date:
                        target_period.end_date = program_date
                    await target_period.save()
                else:
                    # マージ先にも期間がない場合はスキップ (通常は発生しない)
                    logging.warning(
                        f'[SeriesRouter][SeriesMergeAPI] Cannot assign program without channel. '
                        f'[program_id: {program.id}]'
                    )
                    continue

        # 番組をマージ先シリーズに紐付ける
        program.series_id = target_series_id  # type: ignore
        program.series_broadcast_period_id = target_period.id  # type: ignore
        program.series_title = target_series.title
        program.is_series_manually_edited = True
        await program.save()

    # マージ元の SeriesBroadcastPeriod とシリーズ本体を削除
    # RecordedProgram は既に全てマージ先に移動済みなので、CASCADE 削除の問題はない
    await SeriesBroadcastPeriod.filter(series_id=source_series_id).delete()
    await Series.filter(id=source_series_id).delete()

    logging.info(
        f'[SeriesRouter][SeriesMergeAPI] Series merged. '
        f'[source_series_id: {source_series_id}, target_series_id: {target_series_id}, '
        f'programs_moved: {len(source_programs)}]'
    )

    # マージ後のターゲットシリーズを prefetch 込みで返す (フィルターなし版を使用)
    merged_series = await __buildSeriesQuerySetUnfiltered() \
        .get_or_none(id=target_series_id)
    if merged_series is None:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail = 'Target series not found after merge',
        )

    return merged_series
