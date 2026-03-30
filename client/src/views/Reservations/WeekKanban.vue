<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="kanban-wrapper">
                <SPHeaderBar />
                <div class="kanban-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: '録画予約', path: '/reservations/' },
                        { name: '週間カレンダー', path: '/reservations/week', disabled: true },
                    ]" />

                    <!-- ページヘッダー：タイトル + 週ナビゲーション -->
                    <div class="kanban-header">
                        <h2 class="kanban-header__title">
                            <!-- スマホ版のみ表示する戻るボタン -->
                            <div v-ripple class="kanban-header__back" @click="$router.back()">
                                <Icon icon="fluent:chevron-left-12-filled" width="27px" />
                            </div>
                            週間カレンダー
                            <span class="kanban-header__count">
                                <Icon v-if="isLoading" icon="line-md:loading-twotone-loop" class="kanban-header__count-spin" width="18px" height="18px" />
                                <template v-else>{{ allReservations.length }}件</template>
                            </span>
                        </h2>
                        <div class="kanban-header__nav">
                            <v-btn icon variant="text" size="small" @click="prevWeek" aria-label="前週">
                                <Icon icon="fluent:chevron-left-20-regular" width="22px" />
                            </v-btn>
                            <span class="kanban-header__week-label">{{ weekLabel }}</span>
                            <v-btn icon variant="text" size="small" @click="nextWeek" aria-label="次週">
                                <Icon icon="fluent:chevron-right-20-regular" width="22px" />
                            </v-btn>
                            <v-btn v-if="!isCurrentWeek" variant="tonal" size="small" color="primary"
                                class="kanban-header__today-btn" @click="goToCurrentWeek">
                                今週
                            </v-btn>
                        </div>
                    </div>

                    <!-- カンバンボード本体：7列を横スクロール可能なコンテナに配置 -->
                    <div class="kanban-board">
                        <div v-for="(day, idx) in weekDays" :key="idx"
                            class="kanban-column"
                            :class="{
                                'kanban-column--today': isToday(day),
                                'kanban-column--past': isPast(day),
                                'kanban-column--sunday': day.day() === 0,
                                'kanban-column--saturday': day.day() === 6,
                            }">

                            <!-- 列ヘッダー：曜日・日付・予約件数バッジ -->
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
                                <!-- 予約なし表示 -->
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
                                    @click="openDetail(res)">

                                    <!-- 時刻 + ステータス -->
                                    <div class="kanban-card__header">
                                        <span class="kanban-card__time">
                                            {{ formatTime(res.program.start_time) }}〜{{ formatTime(res.program.end_time) }}
                                        </span>
                                        <!-- 録画中はアニメーション付きの赤丸ドット -->
                                        <div v-if="res.is_recording_in_progress" class="kanban-card__recording-dot"></div>
                                        <!-- 録画中でなければステータスチップ -->
                                        <v-chip v-else size="x-small" :color="getStatusColor(res)" variant="tonal"
                                            class="kanban-card__status">
                                            <Icon :icon="getStatusIcon(res)" width="10px" height="10px" class="mr-1" />
                                            {{ getStatusLabel(res) }}
                                        </v-chip>
                                    </div>

                                    <!-- チャンネルロゴ + チャンネル名 -->
                                    <div class="kanban-card__channel">
                                        <img class="kanban-card__channel-logo" loading="lazy" decoding="async"
                                            :src="`${Utils.api_base_url}/channels/${res.channel.id}/logo`"
                                            @error="onLogoError">
                                        <span class="kanban-card__channel-name">{{ res.channel.name }}</span>
                                    </div>

                                    <!-- 番組タイトル -->
                                    <div class="kanban-card__title">{{ res.program.title }}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>

        <!-- 録画予約詳細ドロワー -->
        <ReservationDetailDrawer
            v-model="drawerOpen"
            :reservation="selectedReservation"
            @deleted="handleDeleted"
            @updated="handleUpdated" />
    </div>
</template>

<script lang="ts" setup>

import { ref, computed, onMounted, onUnmounted } from 'vue';

import type { Dayjs } from 'dayjs';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import ReservationDetailDrawer from '@/components/Reservations/ReservationDetailDrawer.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import Reservations, { IReservation } from '@/services/Reservations';
import Utils from '@/utils';
import { dayjs } from '@/utils';

// 曜日名 (インデックス 0=日曜〜6=土曜)
const DAY_NAMES = ['日', '月', '火', '水', '木', '金', '土'];

// 全録画予約データ
const allReservations = ref<IReservation[]>([]);
// ローディング状態
const isLoading = ref(true);

// 詳細ドロワーの状態
const drawerOpen = ref(false);
const selectedReservation = ref<IReservation | null>(null);

// 自動更新タイマー
const autoRefreshInterval = ref<number | null>(null);
const AUTO_REFRESH_INTERVAL = 30 * 1000;  // 30秒

// 現在表示している週の開始日 (日曜日)
// dayjs().startOf('week') はデフォルトで日曜日を返す
const weekStart = ref<Dayjs>(dayjs().startOf('week'));

// 週の 7 日間 (日〜土)
const weekDays = computed<Dayjs[]>(() =>
    Array.from({ length: 7 }, (_, i) => weekStart.value.add(i, 'day')),
);

// ヘッダーに表示する週ラベル (例: 2026/03/29 〜 04/04)
const weekLabel = computed(() => {
    const start = weekStart.value;
    const end = start.add(6, 'day');
    if (start.month() === end.month()) {
        return `${start.format('YYYY/MM/DD')} 〜 ${end.format('DD')}`;
    }
    return `${start.format('YYYY/MM/DD')} 〜 ${end.format('MM/DD')}`;
});

// 表示中の週が今週かどうか
const isCurrentWeek = computed(() =>
    weekStart.value.isSame(dayjs().startOf('week'), 'day'),
);

// 指定した日が今日かどうか
const isToday = (day: Dayjs): boolean => day.isSame(dayjs(), 'day');

// 指定した日が過去かどうか (今日より前)
const isPast = (day: Dayjs): boolean => day.isBefore(dayjs(), 'day');

// 指定した日に放送開始する予約を時刻順で返す
const getReservationsForDay = (day: Dayjs): IReservation[] =>
    allReservations.value
        .filter(res => dayjs(res.program.start_time).isSame(day, 'day'))
        .sort((a, b) => dayjs(a.program.start_time).valueOf() - dayjs(b.program.start_time).valueOf());

// ISO 日時文字列を HH:MM 形式にフォーマット
const formatTime = (iso: string): string => dayjs(iso).format('HH:mm');

// 予約ステータスのラベル (カードに表示する短縮版)
const getStatusLabel = (res: IReservation): string => {
    switch (res.recording_availability) {
        case 'Full':        return '録画可';
        case 'Partial':     return '一部';
        case 'Unavailable': return '不可';
        default:            return '不明';
    }
};

// 予約ステータスのアイコン
const getStatusIcon = (res: IReservation): string => {
    switch (res.recording_availability) {
        case 'Full':        return 'fluent:checkmark-16-filled';
        case 'Partial':     return 'fluent:warning-16-filled';
        case 'Unavailable': return 'fluent:dismiss-circle-16-filled';
        default:            return 'fluent:question-circle-16-filled';
    }
};

// 予約ステータスの色
const getStatusColor = (res: IReservation): string => {
    switch (res.recording_availability) {
        case 'Full':        return 'success';
        case 'Partial':     return 'warning';
        case 'Unavailable': return 'error';
        default:            return 'grey';
    }
};

// チャンネルロゴ読み込み失敗時のフォールバック
const onLogoError = (event: Event) => {
    (event.target as HTMLImageElement).src = `${Utils.api_base_url}/channels/gr001/logo`;
};

// 詳細ドロワーを開く
const openDetail = (res: IReservation) => {
    selectedReservation.value = res;
    drawerOpen.value = true;
};

// ドロワーからの削除イベント処理
const handleDeleted = (id: number) => {
    allReservations.value = allReservations.value.filter(r => r.id !== id);
    drawerOpen.value = false;
};

// ドロワーからの更新イベント処理
const handleUpdated = (updated: IReservation) => {
    const idx = allReservations.value.findIndex(r => r.id === updated.id);
    if (idx !== -1) {
        allReservations.value[idx] = updated;
    }
    selectedReservation.value = updated;
};

// 前週へ移動
const prevWeek = () => { weekStart.value = weekStart.value.subtract(7, 'day'); };

// 次週へ移動
const nextWeek = () => { weekStart.value = weekStart.value.add(7, 'day'); };

// 今週へ戻る
const goToCurrentWeek = () => { weekStart.value = dayjs().startOf('week'); };

// 録画予約データを取得する
const fetchReservations = async () => {
    const result = await Reservations.fetchReservations();
    if (result) {
        allReservations.value = result.reservations;
    }
    isLoading.value = false;
};

// 自動更新を開始
const startAutoRefresh = () => {
    if (autoRefreshInterval.value !== null) return;
    fetchReservations();
    autoRefreshInterval.value = window.setInterval(fetchReservations, AUTO_REFRESH_INTERVAL);
};

// 自動更新を停止
const stopAutoRefresh = () => {
    if (autoRefreshInterval.value !== null) {
        clearInterval(autoRefreshInterval.value);
        autoRefreshInterval.value = null;
    }
};

onMounted(() => startAutoRefresh());
onUnmounted(() => stopAutoRefresh());

</script>
<style lang="scss" scoped>

.kanban-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
    min-width: 0;
}

.kanban-container {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    padding: 20px;
    @include smartphone-horizontal {
        padding: 16px 20px !important;
    }
    @include smartphone-horizontal-short {
        padding: 16px 16px !important;
    }
    @include smartphone-vertical {
        padding: 16px 8px !important;
        padding-top: 8px !important;
    }
}

// ページヘッダー
.kanban-header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 0px;
    padding-bottom: 16px;
    @include smartphone-vertical {
        padding: 0px 8px 12px;
        flex-direction: column;
        align-items: flex-start;
    }

    &__title {
        display: flex;
        align-items: center;
        font-size: 24px;
        font-weight: 700;
        padding-top: 8px;
        position: relative;
        @include smartphone-vertical {
            font-size: 22px;
        }
    }

    // スマホ縦画面でのみ表示する戻るボタン
    &__back {
        display: none;
        position: absolute;
        left: -8px;
        padding: 6px;
        border-radius: 50%;
        color: rgb(var(--v-theme-text));
        cursor: pointer;
        @include smartphone-vertical {
            display: flex;
        }

        & + .kanban-header__title {
            @include smartphone-vertical {
                margin-left: 32px;
            }
        }
    }

    // 「32件」などの件数表示
    &__count {
        display: flex;
        align-items: center;
        padding-top: 8px;
        margin-left: 12px;
        font-size: 14px;
        font-weight: 400;
        color: rgb(var(--v-theme-text-darken-1));

        &-spin {
            animation: kanban-spin 1.15s linear infinite;
        }
        @keyframes kanban-spin {
            from { transform: rotate(0deg); }
            to   { transform: rotate(360deg); }
        }
    }

    // 前週・次週・今週ナビゲーション
    &__nav {
        display: flex;
        align-items: center;
        gap: 4px;
        margin-left: auto;
        @include smartphone-vertical {
            margin-left: 0;
        }
    }

    &__week-label {
        font-size: 15px;
        font-weight: 600;
        color: rgb(var(--v-theme-text));
        min-width: 175px;
        text-align: center;
        @include smartphone-vertical {
            font-size: 14px;
            min-width: 160px;
        }
    }

    &__today-btn {
        margin-left: 4px;
        font-size: 13px;
    }
}

// カンバンボード本体：横スクロール可能な 7 列レイアウト
.kanban-board {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    // スクロールバーを常時表示してスクロール可能であることを示す
    padding-bottom: 8px;
    align-items: flex-start;

    // スクロールバーのスタイリング
    &::-webkit-scrollbar {
        height: 6px;
    }
    &::-webkit-scrollbar-track {
        background: rgb(var(--v-theme-background));
        border-radius: 3px;
    }
    &::-webkit-scrollbar-thumb {
        background: rgb(var(--v-theme-background-lighten-2));
        border-radius: 3px;
    }
}

// 各曜日の列
.kanban-column {
    display: flex;
    flex-direction: column;
    // PC では 7 列が均等に収まるよう flex: 1 で伸長し、最小幅は 130px
    flex: 1 1 0;
    min-width: 130px;
    max-width: 200px;
    background: rgb(var(--v-theme-background-lighten-1));
    border-radius: 8px;
    overflow: hidden;
    @include smartphone-vertical {
        // スマホでは固定幅で横スクロール
        flex: 0 0 140px;
        min-width: 140px;
        max-width: 140px;
    }

    // 今日の列を強調表示
    &--today {
        background: rgba(var(--v-theme-primary), 0.08);
        outline: 2px solid rgba(var(--v-theme-primary), 0.5);
        outline-offset: -2px;

        .kanban-column__header {
            background: rgba(var(--v-theme-primary), 0.15);
        }
        .kanban-column__weekday {
            color: rgb(var(--v-theme-primary));
            font-weight: 800;
        }
        .kanban-column__date {
            color: rgb(var(--v-theme-primary));
            font-weight: 700;
        }
    }

    // 過去の列をやや暗く
    &--past {
        opacity: 0.6;
    }

    // 日曜の曜日名は赤系
    &--sunday .kanban-column__weekday {
        color: #EF5350;
    }

    // 土曜の曜日名は青系
    &--saturday .kanban-column__weekday {
        color: #42A5F5;
    }

    // 列ヘッダー
    &__header {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        padding: 8px 6px 7px;
        background: rgb(var(--v-theme-background-lighten-2));
        flex-shrink: 0;
    }

    &__weekday {
        font-size: 14px;
        font-weight: 700;
        color: rgb(var(--v-theme-text));
    }

    &__date {
        font-size: 13px;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__badge {
        font-size: 10px !important;
        height: 16px !important;
        padding: 0 5px !important;
    }

    // カードコンテナ
    &__cards {
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding: 6px;
        min-height: 80px;
    }

    // 予約なし表示
    &__empty {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 16px 0px;
        color: rgb(var(--v-theme-text-darken-1));
        opacity: 0.4;
    }
}

// 各予約カード
.kanban-card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 7px 8px;
    background: rgb(var(--v-theme-background));
    border-radius: 6px;
    cursor: pointer;
    transition: background-color 0.15s;
    border-left: 3px solid rgb(var(--v-theme-primary));

    &:hover {
        background: rgb(var(--v-theme-background-lighten-2));
    }
    @media (hover: none) {
        &:hover { background: rgb(var(--v-theme-background)); }
    }

    // 録画中カード：左ボーダーを赤に
    &--recording {
        border-left-color: #EF5350;
    }

    // チューナー不足カード：左ボーダーを橙に
    &--unavailable {
        border-left-color: rgb(var(--v-theme-error));
    }

    // 無効カード：透明度を下げる
    &--disabled {
        opacity: 0.55;
    }

    // 時刻 + ステータスチップの行
    &__header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 4px;
    }

    &__time {
        font-size: 11px;
        color: rgb(var(--v-theme-text-darken-1));
        white-space: nowrap;
        flex-shrink: 0;
    }

    &__status {
        font-size: 10px !important;
        height: 16px !important;
        padding: 0 4px !important;
        flex-shrink: 0;
    }

    // 録画中を示す赤丸ドット
    &__recording-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background-color: #EF5350;
        flex-shrink: 0;
        animation: kanban-recording-pulse 2s infinite ease-in-out;
    }
    @keyframes kanban-recording-pulse {
        0%   { background-color: rgba(239, 83, 80, 0.7); }
        50%  { background-color: rgba(239, 83, 80, 1.0); }
        100% { background-color: rgba(239, 83, 80, 0.7); }
    }

    // チャンネルロゴ + チャンネル名の行
    &__channel {
        display: flex;
        align-items: center;
        gap: 4px;
        min-width: 0;
    }

    &__channel-logo {
        flex-shrink: 0;
        width: 22px;
        height: 12px;
        border-radius: 2px;
        object-fit: cover;
        background: linear-gradient(150deg, rgb(var(--v-theme-gray)), rgb(var(--v-theme-background-lighten-2)));
    }

    &__channel-name {
        font-size: 11px;
        color: rgb(var(--v-theme-text-darken-1));
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    // 番組タイトル：最大 3 行まで表示
    &__title {
        font-size: 12px;
        font-weight: 600;
        line-height: 1.4;
        font-feature-settings: 'palt' 1;
        letter-spacing: 0.04em;
        color: rgb(var(--v-theme-text));
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
    }
}

</style>
