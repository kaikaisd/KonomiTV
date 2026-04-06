<template>
    <!-- 録画番組カンバンボード：週ナビゲーション + 7列ボード -->
    <div class="video-kanban-panel">

        <!-- 週ナビゲーションヘッダー -->
        <div class="video-kanban-panel__nav">
            <v-btn icon variant="text" size="small" @click="prevWeek" aria-label="前週">
                <Icon icon="fluent:chevron-left-20-regular" width="22px" />
            </v-btn>
            <span class="video-kanban-panel__week-label">{{ weekLabel }}</span>
            <v-btn icon variant="text" size="small" @click="nextWeek" aria-label="次週">
                <Icon icon="fluent:chevron-right-20-regular" width="22px" />
            </v-btn>
            <v-btn v-if="!isCurrentWeek" variant="tonal" size="x-small" color="primary"
                class="video-kanban-panel__today-btn" @click="goToCurrentWeek">
                今日
            </v-btn>
        </div>

        <!-- 7列ボード：横スクロール可能 -->
        <div class="video-kanban-board">
            <div v-for="(day, idx) in weekDays" :key="idx"
                class="video-kanban-column"
                :class="{
                    'video-kanban-column--today': isToday(day),
                    'video-kanban-column--past': isPast(day),
                    'video-kanban-column--sunday': day.day() === 0,
                    'video-kanban-column--saturday': day.day() === 6,
                }">

                <!-- 列ヘッダー：曜日・日付・件数バッジ -->
                <div class="video-kanban-column__header">
                    <span class="video-kanban-column__weekday">{{ DAY_NAMES[day.day()] }}</span>
                    <span class="video-kanban-column__date">{{ day.format('M/D') }}</span>
                    <v-chip v-if="getProgramsForDay(day).length > 0"
                        size="x-small" color="primary" variant="tonal"
                        class="video-kanban-column__badge">
                        {{ getProgramsForDay(day).length }}
                    </v-chip>
                </div>

                <!-- カード一覧 -->
                <div class="video-kanban-column__cards">
                    <!-- 番組なし・ロード完了後に表示 -->
                    <div v-if="getProgramsForDay(day).length === 0 && !isLoading"
                        class="video-kanban-column__empty">
                        <Icon icon="fluent:video-off-20-regular" width="22px" height="22px" />
                    </div>

                    <!-- 録画番組カード -->
                    <div v-for="program in getProgramsForDay(day)" :key="program.id"
                        v-ripple
                        class="video-kanban-card"
                        :class="{
                            'video-kanban-card--recording': program.recorded_video.status === 'Recording',
                            'video-kanban-card--failed': program.recorded_video.status === 'AnalysisFailed',
                            'video-kanban-card--partial': program.is_partially_recorded,
                        }"
                        @click="$router.push(`/videos/watch/${program.id}`)">

                        <!-- サムネイル（16:9 比率） -->
                        <div class="video-kanban-card__thumbnail">
                            <img class="video-kanban-card__thumbnail-img" loading="lazy" decoding="async"
                                :src="`${Utils.api_base_url}/videos/${program.id}/thumbnail`">
                            <!-- 録画時間バッジ（右下） -->
                            <div class="video-kanban-card__thumbnail-duration">
                                {{ formatDuration(program.recorded_video.duration) }}
                            </div>
                            <!-- 録画中：パルスアニメーション付き赤丸ドット（左上） -->
                            <div v-if="program.recorded_video.status === 'Recording'"
                                class="video-kanban-card__thumbnail-recording">
                                <div class="video-kanban-card__recording-dot"></div>
                                録画中
                            </div>
                            <!-- 解析失敗オーバーレイ -->
                            <div v-else-if="program.recorded_video.status === 'AnalysisFailed'"
                                class="video-kanban-card__thumbnail-overlay video-kanban-card__thumbnail-overlay--failed">
                                <Icon icon="fluent:warning-16-filled" width="12px" height="12px" />
                                解析失敗
                            </div>
                            <!-- 部分録画オーバーレイ -->
                            <div v-else-if="program.is_partially_recorded"
                                class="video-kanban-card__thumbnail-overlay video-kanban-card__thumbnail-overlay--partial">
                                ⚠️ 一部
                            </div>
                        </div>

                        <!-- カード下部：チャンネル + タイトル -->
                        <div class="video-kanban-card__body">
                            <!-- 時刻 -->
                            <div class="video-kanban-card__time">
                                {{ formatTime(program.start_time) }}〜{{ formatTime(program.end_time) }}
                            </div>
                            <!-- チャンネルロゴ + チャンネル名 -->
                            <div v-if="program.channel" class="video-kanban-card__channel">
                                <img class="video-kanban-card__channel-logo" loading="lazy" decoding="async"
                                    :src="`${Utils.api_base_url}/channels/${program.channel.id}/logo`"
                                    @error="onLogoError">
                                <span class="video-kanban-card__channel-name">{{ program.channel.name }}</span>
                            </div>
                            <!-- 番組タイトル（最大2行） -->
                            <div class="video-kanban-card__title">{{ program.title }}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script lang="ts" setup>

import { ref, computed } from 'vue';

import type { Dayjs } from 'dayjs';

import { IRecordedProgram } from '@/services/Videos';
import Utils from '@/utils';
import { dayjs } from '@/utils';

// Props
const props = defineProps<{
    // 表示する録画番組リスト (親コンポーネントから渡す)
    programs: IRecordedProgram[];
    // ロード中かどうか (true のとき空列の「番組なし」表示を抑制する)
    isLoading: boolean;
}>();

// 曜日名 (0=日曜〜6=土曜)
const DAY_NAMES = ['日', '月', '火', '水', '木', '金', '土'];

// 現在表示中の週の開始日 (デフォルトは今日)
const weekStart = ref<Dayjs>(dayjs().startOf('day'));

// 7 日間 (今日 〜 T+6)
const weekDays = computed<Dayjs[]>(() =>
    Array.from({ length: 7 }, (_, i) => weekStart.value.add(i, 'day')),
);

// 週ラベル (例: 2026/03/29 〜 04/04)
const weekLabel = computed(() => {
    const start = weekStart.value;
    const end = start.add(6, 'day');
    if (start.month() === end.month()) {
        return `${start.format('YYYY/MM/DD')} 〜 ${end.format('DD')}`;
    }
    return `${start.format('YYYY/MM/DD')} 〜 ${end.format('MM/DD')}`;
});

// 今日始まりかどうか
const isCurrentWeek = computed(() =>
    weekStart.value.isSame(dayjs(), 'day'),
);

const isToday = (day: Dayjs): boolean => day.isSame(dayjs(), 'day');
const isPast  = (day: Dayjs): boolean => day.isBefore(dayjs(), 'day');

// 指定日の録画番組を開始時刻順で返す
const getProgramsForDay = (day: Dayjs): IRecordedProgram[] =>
    props.programs
        .filter(p => dayjs(p.start_time).isSame(day, 'day'))
        .sort((a, b) => dayjs(a.start_time).valueOf() - dayjs(b.start_time).valueOf());

const formatTime = (iso: string): string => dayjs(iso).format('HH:mm');

// 録画時間を分単位で整形する (例: 30分, 1時間30分)
const formatDuration = (seconds: number): string => {
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes}分`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}時間${m}分` : `${h}時間`;
};

const onLogoError = (event: Event) => {
    (event.target as HTMLImageElement).src = `${Utils.api_base_url}/channels/gr001/logo`;
};

const prevWeek = () => { weekStart.value = weekStart.value.subtract(7, 'day'); };
const nextWeek = () => { weekStart.value = weekStart.value.add(7, 'day'); };
const goToCurrentWeek = () => { weekStart.value = dayjs().startOf('day'); };

</script>
<style lang="scss" scoped>

.video-kanban-panel {
    display: flex;
    flex-direction: column;
    width: 100%;
    min-width: 0;

    // 週ナビゲーションヘッダー
    &__nav {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 4px;
        margin-bottom: 10px;
    }

    &__week-label {
        font-size: 14px;
        font-weight: 600;
        color: rgb(var(--v-theme-text));
        min-width: 165px;
        text-align: center;
    }

    &__today-btn {
        margin-left: 4px;
        font-size: 12px;
    }
}

// カンバンボード本体：7列を横スクロール可能に配置
.video-kanban-board {
    display: flex;
    gap: 5px;
    overflow-x: auto;
    padding-bottom: 6px;
    align-items: flex-start;

    &::-webkit-scrollbar        { height: 5px; }
    &::-webkit-scrollbar-track  { background: rgb(var(--v-theme-background)); border-radius: 3px; }
    &::-webkit-scrollbar-thumb  { background: rgb(var(--v-theme-background-lighten-2)); border-radius: 3px; }
}

// 各曜日列
.video-kanban-column {
    display: flex;
    flex-direction: column;
    flex: 1 1 0;
    min-width: 120px;
    max-width: 180px;
    background: rgb(var(--v-theme-background-lighten-1));
    border-radius: 8px;
    overflow: hidden;

    // 今日の列を強調
    &--today {
        background: rgba(var(--v-theme-primary), 0.08);
        outline: 2px solid rgba(var(--v-theme-primary), 0.5);
        outline-offset: -2px;

        .video-kanban-column__header {
            background: rgba(var(--v-theme-primary), 0.15);
        }
        .video-kanban-column__weekday,
        .video-kanban-column__date {
            color: rgb(var(--v-theme-primary));
            font-weight: 800;
        }
    }

    // 過去の列は透過
    &--past { opacity: 0.6; }

    // 日曜：赤系、土曜：青系
    &--sunday   .video-kanban-column__weekday { color: #EF5350; }
    &--saturday .video-kanban-column__weekday { color: #42A5F5; }

    // 列ヘッダー
    &__header {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        padding: 7px 6px;
        background: rgb(var(--v-theme-background-lighten-2));
        flex-shrink: 0;
    }

    &__weekday {
        font-size: 13px;
        font-weight: 700;
        color: rgb(var(--v-theme-text));
    }

    &__date {
        font-size: 12px;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__badge {
        font-size: 10px !important;
        height: 15px !important;
        padding: 0 4px !important;
    }

    // カードコンテナ
    &__cards {
        display: flex;
        flex-direction: column;
        gap: 5px;
        padding: 5px;
        min-height: 60px;
    }

    // 番組なし表示
    &__empty {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 14px 0;
        color: rgb(var(--v-theme-text-darken-1));
        opacity: 0.35;
    }
}

// 録画番組カード（サムネイル付きカードビュー）
.video-kanban-card {
    display: flex;
    flex-direction: column;
    background: rgb(var(--v-theme-background));
    border-radius: 6px;
    cursor: pointer;
    transition: background-color 0.15s;
    overflow: hidden;
    border-left: 3px solid rgb(var(--v-theme-primary));

    &:hover { background: rgb(var(--v-theme-background-lighten-2)); }
    @media (hover: none) {
        &:hover { background: rgb(var(--v-theme-background)); }
    }

    // 録画中：赤いボーダー
    &--recording  { border-left-color: #EF5350; }
    // 解析失敗：オレンジ
    &--failed     { border-left-color: rgb(var(--v-theme-warning)); opacity: 0.8; }
    // 部分録画：警告色
    &--partial    { border-left-color: rgb(var(--v-theme-warning)); }

    // サムネイル領域（16:9 比率）
    &__thumbnail {
        position: relative;
        width: 100%;
        aspect-ratio: 16 / 9;
        overflow: hidden;
        background: rgb(var(--v-theme-background-lighten-2));
        flex-shrink: 0;
    }

    &__thumbnail-img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }

    // 録画時間バッジ（右下）
    &__thumbnail-duration {
        position: absolute;
        bottom: 4px;
        right: 4px;
        background: rgba(0, 0, 0, 0.72);
        color: #fff;
        font-size: 9.5px;
        font-weight: 600;
        padding: 1px 4px;
        border-radius: 3px;
        line-height: 1.5;
        pointer-events: none;
    }

    // 録画中バッジ（左上）
    &__thumbnail-recording {
        position: absolute;
        top: 4px;
        left: 4px;
        display: flex;
        align-items: center;
        gap: 3px;
        background: rgba(239, 83, 80, 0.88);
        color: #fff;
        font-size: 9px;
        font-weight: 700;
        padding: 2px 5px;
        border-radius: 3px;
        pointer-events: none;
    }

    // ステータスオーバーレイ（左上）
    &__thumbnail-overlay {
        position: absolute;
        top: 4px;
        left: 4px;
        display: flex;
        align-items: center;
        gap: 3px;
        font-size: 9px;
        font-weight: 700;
        padding: 2px 5px;
        border-radius: 3px;
        pointer-events: none;

        &--failed  { background: rgba(var(--v-theme-warning), 0.9); color: #fff; }
        &--partial { background: rgba(0, 0, 0, 0.65); color: #fff; }
    }

    // 録画中：パルスアニメーションの赤丸
    &__recording-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background-color: #fff;
        flex-shrink: 0;
        animation: video-kanban-pulse 2s infinite ease-in-out;
    }
    @keyframes video-kanban-pulse {
        0%   { opacity: 0.6; }
        50%  { opacity: 1.0; }
        100% { opacity: 0.6; }
    }

    // カード下部テキスト領域
    &__body {
        display: flex;
        flex-direction: column;
        gap: 3px;
        padding: 5px 6px 6px;
    }

    // 時刻
    &__time {
        font-size: 10px;
        color: rgb(var(--v-theme-text-darken-1));
        white-space: nowrap;
    }

    // チャンネル行
    &__channel {
        display: flex;
        align-items: center;
        gap: 3px;
        min-width: 0;
    }

    &__channel-logo {
        flex-shrink: 0;
        width: 18px;
        height: 10px;
        border-radius: 2px;
        object-fit: cover;
        background: linear-gradient(150deg, rgb(var(--v-theme-gray)), rgb(var(--v-theme-background-lighten-2)));
    }

    &__channel-name {
        font-size: 10px;
        color: rgb(var(--v-theme-text-darken-1));
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    // タイトル（最大2行）
    &__title {
        font-size: 11px;
        font-weight: 600;
        line-height: 1.4;
        font-feature-settings: 'palt' 1;
        letter-spacing: 0.02em;
        color: rgb(var(--v-theme-text));
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
    }
}

</style>
