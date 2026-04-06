<template>
    <!-- カンバンボードパネル：週ナビゲーション + 7列ボード -->
    <div class="kanban-panel">

        <!-- 週ナビゲーションヘッダー -->
        <div class="kanban-panel__nav">
            <v-btn icon variant="text" size="small" @click="prevWeek" aria-label="前週">
                <Icon icon="fluent:chevron-left-20-regular" width="22px" />
            </v-btn>
            <span class="kanban-panel__week-label">{{ weekLabel }}</span>
            <v-btn icon variant="text" size="small" @click="nextWeek" aria-label="次週">
                <Icon icon="fluent:chevron-right-20-regular" width="22px" />
            </v-btn>
            <v-btn v-if="!isCurrentWeek" variant="tonal" size="x-small" color="primary"
                class="kanban-panel__today-btn" @click="goToCurrentWeek">
                今日
            </v-btn>
        </div>

        <!-- 7列ボード：横スクロール可能 -->
        <div class="kanban-board">
            <div v-for="(day, idx) in weekDays" :key="idx"
                class="kanban-column"
                :class="{
                    'kanban-column--today': isToday(day),
                    'kanban-column--past': isPast(day),
                    'kanban-column--sunday': day.day() === 0,
                    'kanban-column--saturday': day.day() === 6,
                }">

                <!-- 列ヘッダー：曜日・日付・件数バッジ -->
                <div class="kanban-column__header">
                    <span class="kanban-column__weekday">{{ DAY_NAMES[day.day()] }}</span>
                    <span class="kanban-column__date">{{ day.format('M/D') }}</span>
                    <v-chip v-if="getReservationsForDay(day).length > 0"
                        size="x-small" color="primary" variant="tonal"
                        class="kanban-column__badge">
                        {{ getReservationsForDay(day).length }}
                    </v-chip>
                </div>

                <!-- カード一覧 -->
                <div class="kanban-column__cards">
                    <!-- 予約なし・ロード完了後に表示 -->
                    <div v-if="getReservationsForDay(day).length === 0 && !isLoading"
                        class="kanban-column__empty">
                        <Icon icon="fluent:calendar-empty-20-regular" width="22px" height="22px" />
                    </div>

                    <!-- 予約カード -->
                    <div v-for="res in getReservationsForDay(day)" :key="res.id"
                        v-ripple
                        class="kanban-card"
                        :class="{
                            'kanban-card--recording': res.is_recording_in_progress,
                            'kanban-card--unavailable': res.recording_availability === 'Unavailable',
                            'kanban-card--disabled': !res.record_settings.is_enabled,
                        }"
                        @click="$emit('clickReservation', res)">

                        <!-- 時刻・ステータス行（中央揃え） -->
                        <div class="kanban-card__header">
                            <span class="kanban-card__time">
                                {{ formatTime(res.program.start_time) }}〜{{ formatTime(res.program.end_time) }}
                            </span>
                            <!-- 録画中：パルスアニメーション付き赤丸ドット -->
                            <div v-if="res.is_recording_in_progress" class="kanban-card__recording-dot"></div>
                            <!-- 通常：ステータスチップ -->
                            <v-chip v-else size="x-small" :color="getStatusColor(res)" variant="tonal"
                                class="kanban-card__status">
                                <Icon :icon="getStatusIcon(res)" width="10px" height="10px" class="mr-1" />
                                {{ getStatusLabel(res) }}
                            </v-chip>
                        </div>

                        <!-- チャンネルロゴ + チャンネル名（中央揃え） -->
                        <div class="kanban-card__channel">
                            <img class="kanban-card__channel-logo" loading="lazy" decoding="async"
                                :src="`${Utils.api_base_url}/channels/${res.channel.id}/logo`"
                                @error="onLogoError">
                            <span class="kanban-card__channel-name">{{ res.channel.name }}</span>
                        </div>

                        <!-- 番組タイトル（中央揃え・最大3行） -->
                        <div class="kanban-card__title">{{ res.program.title }}</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script lang="ts" setup>

import { ref, computed } from 'vue';

import type { Dayjs } from 'dayjs';

import { IReservation } from '@/services/Reservations';
import Utils from '@/utils';
import { dayjs } from '@/utils';

// Props
const props = defineProps<{
    // 表示する録画予約リスト (親コンポーネントから渡す)
    reservations: IReservation[];
    // ロード中かどうか (true のとき空列の「予約なし」表示を抑制する)
    isLoading: boolean;
}>();

// Emits
defineEmits<{
    // カードクリック時に対象予約を親へ通知する
    (e: 'clickReservation', reservation: IReservation): void;
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

// 指定日の予約を開始時刻順で返す
const getReservationsForDay = (day: Dayjs): IReservation[] =>
    props.reservations
        .filter(res => dayjs(res.program.start_time).isSame(day, 'day'))
        .sort((a, b) => dayjs(a.program.start_time).valueOf() - dayjs(b.program.start_time).valueOf());

const formatTime = (iso: string): string => dayjs(iso).format('HH:mm');

const getStatusLabel = (res: IReservation): string => {
    switch (res.recording_availability) {
        case 'Full':        return '録画可';
        case 'Partial':     return '一部';
        case 'Unavailable': return '不可';
        default:            return '不明';
    }
};
const getStatusIcon = (res: IReservation): string => {
    switch (res.recording_availability) {
        case 'Full':        return 'fluent:checkmark-16-filled';
        case 'Partial':     return 'fluent:warning-16-filled';
        case 'Unavailable': return 'fluent:dismiss-circle-16-filled';
        default:            return 'fluent:question-circle-16-filled';
    }
};
const getStatusColor = (res: IReservation): string => {
    switch (res.recording_availability) {
        case 'Full':        return 'success';
        case 'Partial':     return 'warning';
        case 'Unavailable': return 'error';
        default:            return 'grey';
    }
};

const onLogoError = (event: Event) => {
    (event.target as HTMLImageElement).src = `${Utils.api_base_url}/channels/gr001/logo`;
};

const prevWeek = () => { weekStart.value = weekStart.value.subtract(7, 'day'); };
const nextWeek = () => { weekStart.value = weekStart.value.add(7, 'day'); };
const goToCurrentWeek = () => { weekStart.value = dayjs().startOf('day'); };

</script>
<style lang="scss" scoped>

.kanban-panel {
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
.kanban-board {
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
.kanban-column {
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

        .kanban-column__header {
            background: rgba(var(--v-theme-primary), 0.15);
        }
        .kanban-column__weekday,
        .kanban-column__date {
            color: rgb(var(--v-theme-primary));
            font-weight: 800;
        }
    }

    // 過去の列は透過
    &--past { opacity: 0.6; }

    // 日曜：赤系、土曜：青系
    &--sunday   .kanban-column__weekday { color: #EF5350; }
    &--saturday .kanban-column__weekday { color: #42A5F5; }

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

    // 予約なし表示
    &__empty {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 14px 0;
        color: rgb(var(--v-theme-text-darken-1));
        opacity: 0.35;
    }
}

// 予約カード（全テキストを中央揃え）
.kanban-card {
    display: flex;
    flex-direction: column;
    align-items: center;      // 子要素を中央揃え
    gap: 3px;
    padding: 6px 7px;
    background: rgb(var(--v-theme-background));
    border-radius: 6px;
    cursor: pointer;
    transition: background-color 0.15s;
    border-left: 3px solid rgb(var(--v-theme-primary));
    text-align: center;       // テキストを中央揃え

    &:hover { background: rgb(var(--v-theme-background-lighten-2)); }
    @media (hover: none) {
        &:hover { background: rgb(var(--v-theme-background)); }
    }

    &--recording  { border-left-color: #EF5350; }
    &--unavailable { border-left-color: rgb(var(--v-theme-error)); }
    &--disabled   { opacity: 0.55; }

    // 時刻 + ステータスの行（中央揃え flex）
    &__header {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 4px;
        width: 100%;
    }

    &__time {
        font-size: 10.5px;
        color: rgb(var(--v-theme-text-darken-1));
        white-space: nowrap;
    }

    &__status {
        font-size: 10px !important;
        height: 15px !important;
        padding: 0 4px !important;
        flex-shrink: 0;
    }

    // 録画中：パルスアニメーションの赤丸
    &__recording-dot {
        width: 9px;
        height: 9px;
        border-radius: 50%;
        background-color: #EF5350;
        flex-shrink: 0;
        animation: kanban-pulse 2s infinite ease-in-out;
    }
    @keyframes kanban-pulse {
        0%   { background-color: rgba(239, 83, 80, 0.7); }
        50%  { background-color: rgba(239, 83, 80, 1.0); }
        100% { background-color: rgba(239, 83, 80, 0.7); }
    }

    // チャンネル行（中央揃え）
    &__channel {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 3px;
        width: 100%;
        min-width: 0;
    }

    &__channel-logo {
        flex-shrink: 0;
        width: 20px;
        height: 11px;
        border-radius: 2px;
        object-fit: cover;
        background: linear-gradient(150deg, rgb(var(--v-theme-gray)), rgb(var(--v-theme-background-lighten-2)));
    }

    &__channel-name {
        font-size: 10.5px;
        color: rgb(var(--v-theme-text-darken-1));
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    // タイトル（中央揃え・最大3行）
    &__title {
        font-size: 11.5px;
        font-weight: 600;
        line-height: 1.4;
        font-feature-settings: 'palt' 1;
        letter-spacing: 0.03em;
        color: rgb(var(--v-theme-text));
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        width: 100%;
    }
}

</style>
