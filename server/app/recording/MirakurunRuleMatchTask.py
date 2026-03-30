
import asyncio
import json
import re as re_module
from datetime import datetime, timedelta
from typing import Any

from tortoise import connections

from app import logging, schemas
from app.constants import JST
from app.utils import ParseDatetimeStringToJST


class MirakurunRuleMatchTask:
    """
    Mirakurun バックエンドのキーワード自動予約ルールに基づき、番組 DB を定期的にスキャンして
    録画予約 (MirakurunReservation) を自動生成するバックグラウンドタスク。
    EPGStation の ReservationManageModel / RuleManageModel に相当する処理を実装する。

    動作概要:
    - SCAN_INTERVAL_SECONDS 秒ごとに全有効ルールをスキャンする
    - 各ルールの ProgramSearchCondition に従って番組 DB をクエリし、マッチした番組を抽出する
    - 既に予約済みでない番組に対して MirakurunReservation レコードを自動生成する
    - duplicate_title_check_scope が設定されている場合は、同タイトルの重複録画を回避する
    """

    # ルールスキャンの間隔 (秒)
    SCAN_INTERVAL_SECONDS: int = 300  # 5分ごと

    # スキャン対象とする番組の先読み日数
    LOOK_AHEAD_DAYS: int = 14

    # バックグラウンドスキャンタスク (クラス変数)
    _task: asyncio.Task[None] | None = None

    @classmethod
    async def start(cls) -> None:
        """
        バックグラウンドスキャンタスクを開始する。
        app.py の Startup() から呼び出される。
        """
        logging.info('MirakurunRuleMatchTask: Starting rule match background task.')
        cls._task = asyncio.create_task(cls._mainLoop())

    @classmethod
    async def stop(cls) -> None:
        """
        バックグラウンドスキャンタスクを停止する。
        app.py の Shutdown() から呼び出される。
        """
        if cls._task is not None:
            cls._task.cancel()
            try:
                await cls._task
            except asyncio.CancelledError:
                pass
            cls._task = None
            logging.info('MirakurunRuleMatchTask: Rule match background task stopped.')

    @classmethod
    async def runNow(cls) -> None:
        """
        ルールマッチングを即座に実行する。
        ルールの追加・更新・削除時に呼び出して、予約リストをすぐ反映させる。
        """
        await cls._processAllRules()

    @classmethod
    async def _mainLoop(cls) -> None:
        """
        メインループ: SCAN_INTERVAL_SECONDS 秒ごとに全ルールを処理する。
        """
        while True:
            try:
                await cls._processAllRules()
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                logging.error('MirakurunRuleMatchTask: Unhandled error in rule match loop.', exc_info=ex)
            await asyncio.sleep(cls.SCAN_INTERVAL_SECONDS)

    @classmethod
    async def _processAllRules(cls) -> None:
        """
        DB 上の全ルールを順に処理して、マッチした番組の予約を生成する。
        無効化 (is_enabled=False) されているルールはスキップする。
        """
        # 循環インポートを避けるため、ここでインポートする
        from app.models.MirakurunRecordingRule import MirakurunRecordingRule

        rules = await MirakurunRecordingRule.all()
        if not rules:
            return

        logging.debug(f'MirakurunRuleMatchTask: Processing {len(rules)} rule(s).')
        for rule in rules:
            condition = rule.getProgramSearchCondition()
            # is_enabled=False のルールはスキップ
            if not condition.is_enabled:
                continue
            try:
                await cls._processRule(rule, condition)
            except Exception as ex:
                logging.error(f'MirakurunRuleMatchTask: Failed to process rule {rule.id}.', exc_info=ex)

    @classmethod
    async def _processRule(
        cls,
        rule: Any,
        condition: schemas.ProgramSearchCondition,
    ) -> None:
        """
        1つのルールを処理して、マッチした番組に対して予約を生成する。

        Args:
            rule (MirakurunRecordingRule): 処理するルール
            condition (schemas.ProgramSearchCondition): デシリアライズ済みの番組検索条件
        """
        now = datetime.now(tz=JST)
        look_ahead = now + timedelta(days=cls.LOOK_AHEAD_DAYS)
        connection = connections.get('default')

        # --- SQL による一次フィルタリング ---
        # service_ranges (チャンネル絞り込み) の WHERE 句を構築する
        service_where = ''
        service_params: list[Any] = []
        if condition.service_ranges:
            clauses = ['(p.network_id = ? AND p.service_id = ?)' for _ in condition.service_ranges]
            service_where = f'AND ({" OR ".join(clauses)})'
            for sr in condition.service_ranges:
                service_params.extend([sr.network_id, sr.service_id])

        # duration_range (番組長絞り込み) の WHERE 句を構築する (DB は秒、スキーマは分)
        duration_where = ''
        if condition.duration_range_min is not None:
            duration_where += f' AND p.duration >= {condition.duration_range_min * 60}'
        if condition.duration_range_max is not None:
            duration_where += f' AND p.duration <= {condition.duration_range_max * 60}'

        # broadcast_type (無料/有料) の WHERE 句を構築する
        free_where = ''
        if condition.broadcast_type == 'FreeOnly':
            free_where = 'AND p.is_free = 1'
        elif condition.broadcast_type == 'PaidOnly':
            free_where = 'AND p.is_free = 0'

        # end_time > now を下限に使うことで、既に放送開始済みだがまだ終了していない番組も対象に含める。
        # start_time > now を使うと、EPG データの到着遅延やスキャン間隔 (5分) の隙間で
        # 放送開始直後の番組がマッチ対象から漏れ、録画が作成されない問題を防ぐ。
        query = f"""
            SELECT
                p.id, p.channel_id, p.network_id, p.service_id, p.event_id,
                p.title, p.description, p.genres,
                p.start_time, p.end_time, p.duration, p.is_free
            FROM programs p
            WHERE
                p.end_time > ?
                AND p.start_time < ?
                {service_where}
                {duration_where}
                {free_where}
            ORDER BY p.start_time
        """
        params: list[Any] = [now.isoformat(), look_ahead.isoformat(), *service_params]
        programs = await connection.execute_query_dict(query, params)

        # --- Python による二次フィルタリング ---
        # キーワード・ジャンル・放送日時の条件はSQLで扱いにくいためPythonで評価する
        for prog in programs:
            if cls._matchesCondition(prog, condition):
                await cls._createReservationIfNeeded(prog, rule, condition)

    @classmethod
    def _matchesCondition(
        cls,
        prog: dict[str, Any],
        condition: schemas.ProgramSearchCondition,
    ) -> bool:
        """
        番組が番組検索条件にマッチするかどうかを評価する。

        Args:
            prog (dict): programs テーブルの1行 (title, description, genres, start_time 等を含む)
            condition (schemas.ProgramSearchCondition): 番組検索条件

        Returns:
            bool: マッチすれば True
        """
        title: str = prog.get('title') or ''
        description: str = prog.get('description') or ''

        # --- キーワードマッチング ---
        keyword = condition.keyword.strip()
        if keyword:
            if condition.is_regex_search_enabled:
                # 正規表現検索
                flags = 0 if condition.is_case_sensitive else re_module.IGNORECASE
                try:
                    pattern = re_module.compile(keyword, flags)
                    found_in_title = bool(pattern.search(title))
                    found_in_desc = bool(pattern.search(description))
                except re_module.error:
                    return False  # 無効な正規表現はスキップ
            elif not condition.is_case_sensitive:
                # 大文字小文字を区別しない検索
                kw_lower = keyword.lower()
                found_in_title = kw_lower in title.lower()
                found_in_desc = kw_lower in description.lower()
            else:
                # 完全一致 (大文字小文字を区別する)
                found_in_title = keyword in title
                found_in_desc = keyword in description

            if condition.is_title_only:
                if not found_in_title:
                    return False
            else:
                if not (found_in_title or found_in_desc):
                    return False

        # --- 除外キーワードマッチング ---
        exclude_keyword = condition.exclude_keyword.strip()
        if exclude_keyword:
            if not condition.is_case_sensitive:
                ex_lower = exclude_keyword.lower()
                if ex_lower in title.lower() or ex_lower in description.lower():
                    return False
            else:
                if exclude_keyword in title or exclude_keyword in description:
                    return False

        # --- ジャンルマッチング ---
        if condition.genre_ranges:
            # genres フィールドは SQLite から文字列または Python リストで返る場合がある
            raw_genres = prog.get('genres')
            genres: list[dict[str, str]] = (
                json.loads(raw_genres) if isinstance(raw_genres, str) else (raw_genres or [])
            )
            genre_match = any(
                any(
                    g.get('major') == gr['major'] and
                    (gr['middle'] == 'その他' or g.get('middle') == gr['middle'])
                    for g in genres
                )
                for gr in condition.genre_ranges
            )
            if condition.is_exclude_genre_ranges:
                if genre_match:
                    return False
            else:
                if not genre_match:
                    return False

        # --- 放送日時範囲マッチング ---
        if condition.date_ranges:
            # DB から来る start_time は文字列か datetime のどちらかになる
            raw_start = prog.get('start_time')
            # start_time が取得できない場合は放送日時範囲チェックをスキップして一致なしとする
            if raw_start is None:
                return False
            start_time = (
                ParseDatetimeStringToJST(raw_start)
                if isinstance(raw_start, str)
                else (raw_start.astimezone(JST) if raw_start.tzinfo is not None else raw_start.replace(tzinfo=JST))
            )

            # Python weekday(): 0=月曜日...6=日曜日 → スキーマ形式: 0=日曜日...6=土曜日
            # (weekday + 1) % 7 で変換する (月曜=0→1, ..., 日曜=6→0)
            schema_day = (start_time.weekday() + 1) % 7
            prog_minutes_of_week = schema_day * 24 * 60 + start_time.hour * 60 + start_time.minute

            date_match = any(
                cls._matchesDateRange(dr, prog_minutes_of_week)
                for dr in condition.date_ranges
            )
            if condition.is_exclude_date_ranges:
                if date_match:
                    return False
            else:
                if not date_match:
                    return False

        return True

    @classmethod
    def _matchesDateRange(
        cls,
        dr: schemas.ProgramSearchConditionDate,
        prog_minutes_of_week: int,
    ) -> bool:
        """
        番組の放送日時 (週内分数) が放送日時範囲にマッチするかどうかを評価する。
        週をまたぐ範囲 (例: 土曜日 22:00 〜 日曜日 02:00) にも対応する。

        Args:
            dr (schemas.ProgramSearchConditionDate): 放送日時範囲
            prog_minutes_of_week (int): 番組の放送開始時刻 (週の開始からの分数, 0=日曜 0:00)

        Returns:
            bool: マッチすれば True
        """
        # スキーマは 0=日曜日...6=土曜日 なので、そのまま週内分数に変換する
        range_start = dr.start_day_of_week * 24 * 60 + dr.start_hour * 60 + dr.start_minute
        range_end = dr.end_day_of_week * 24 * 60 + dr.end_hour * 60 + dr.end_minute

        if range_start <= range_end:
            # 週をまたがない通常の範囲
            return range_start <= prog_minutes_of_week < range_end
        else:
            # 週をまたぐ範囲 (例: 土曜 22:00 〜 日曜 02:00)
            # 週内分数の最大値 = 7 * 24 * 60 = 10080
            return prog_minutes_of_week >= range_start or prog_minutes_of_week < range_end

    @classmethod
    async def _createReservationIfNeeded(
        cls,
        prog: dict[str, Any],
        rule: Any,
        condition: schemas.ProgramSearchCondition,
    ) -> None:
        """
        マッチした番組に対して、既存の予約が存在しない場合に MirakurunReservation を新規作成する。
        duplicate_title_check_scope に従って重複チェックを行う。

        Args:
            prog (dict): programs テーブルの1行
            rule (MirakurunRecordingRule): 予約を生成したルール
            condition (schemas.ProgramSearchCondition): 番組検索条件
        """
        from app.models.MirakurunReservation import MirakurunReservation

        network_id: int = prog['network_id']
        service_id: int = prog['service_id']
        event_id: int = prog['event_id']
        title: str = prog.get('title') or ''
        channel_id: str | None = prog.get('channel_id')

        # --- 同一番組 (NID/SID/EID) の予約重複チェック ---
        # Pending / Recording の状態で既に予約が存在する場合はスキップする
        existing = await MirakurunReservation.filter(
            network_id=network_id,
            service_id=service_id,
            event_id=event_id,
            status__in=['Pending', 'Recording'],
        ).first()
        if existing is not None:
            return

        # --- 同タイトル重複チェック (duplicate_title_check_scope) ---
        if condition.duplicate_title_check_scope != 'None' and title:
            period_days = condition.duplicate_title_check_period_days
            cutoff = datetime.now(tz=JST) - timedelta(days=period_days)

            dup_filter: dict[str, Any] = {
                'title': title,
                'status__in': ['Pending', 'Recording', 'Completed'],
                'created_at__gte': cutoff,
            }
            if condition.duplicate_title_check_scope == 'SameChannelOnly' and channel_id is not None:
                dup_filter['channel_id'] = channel_id

            dup_exists = await MirakurunReservation.filter(**dup_filter).exists()
            if dup_exists:
                return  # 重複タイトルがあればスキップ

        # --- 開始・終了時刻の取得 ---
        raw_start = prog.get('start_time')
        raw_end = prog.get('end_time')
        # start_time / end_time が取得できない場合は予約を生成しない
        if raw_start is None or raw_end is None:
            return
        start_time = (
            ParseDatetimeStringToJST(raw_start)
            if isinstance(raw_start, str)
            else (raw_start.astimezone(JST) if raw_start.tzinfo is not None else raw_start.replace(tzinfo=JST))
        )
        end_time = (
            ParseDatetimeStringToJST(raw_end)
            if isinstance(raw_end, str)
            else (raw_end.astimezone(JST) if raw_end.tzinfo is not None else raw_end.replace(tzinfo=JST))
        )

        # --- 録画設定の取得 ---
        record_settings = rule.getRecordSettings()
        # recording_start_margin / recording_end_margin が None の場合は 0.0 を使用する
        recording_start_margin: float = float(record_settings.recording_start_margin or 0)
        recording_end_margin: float = float(record_settings.recording_end_margin or 0)

        # --- ジャンル情報の取得 ---
        raw_genres = prog.get('genres')
        genres = json.loads(raw_genres) if isinstance(raw_genres, str) else (raw_genres or [])

        # --- MirakurunReservation レコードの作成 ---
        reservation = MirakurunReservation(
            channel_id=channel_id,
            network_id=network_id,
            service_id=service_id,
            event_id=event_id,
            title=title,
            description=prog.get('description') or '',
            genres=genres,
            start_time=start_time,
            end_time=end_time,
            recording_start_margin=recording_start_margin,
            recording_end_margin=recording_end_margin,
            status='Pending',
            comment=f'自動予約ルール ID:{rule.id} / {condition.note}'.strip(' /'),
        )
        reservation.setRecordSettings(record_settings)
        await reservation.save()

        logging.info(
            f'MirakurunRuleMatchTask: Auto-reservation created for rule {rule.id}: '
            f'"{title}" ({start_time.strftime("%Y-%m-%d %H:%M")})'
        )
