<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="video-week-kanban-wrapper">
                <SPHeaderBar />
                <div class="video-week-kanban-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: 'ビデオをみる', path: '/videos/' },
                        { name: '録画番組一覧', path: '/videos/programs' },
                        { name: '週間カレンダー', path: '/videos/week', disabled: true },
                    ]" />

                    <!-- ページヘッダー：タイトル + 件数 -->
                    <div class="video-week-kanban-header">
                        <h2 class="video-week-kanban-header__title">
                            <div v-ripple class="video-week-kanban-header__back" @click="$router.back()">
                                <Icon icon="fluent:chevron-left-12-filled" width="27px" />
                            </div>
                            週間カレンダー
                            <span class="video-week-kanban-header__count">
                                <Icon v-if="isLoading" icon="line-md:loading-twotone-loop"
                                    class="video-week-kanban-header__count-spin" width="18px" height="18px" />
                                <template v-else>{{ allPrograms.length }}件</template>
                            </span>
                        </h2>
                    </div>

                    <!-- カンバンボード本体 -->
                    <VideoKanbanBoard
                        :programs="allPrograms"
                        :isLoading="isLoading" />
                </div>
            </div>
        </main>
    </div>
</template>

<script lang="ts" setup>

import { ref, onMounted, onUnmounted } from 'vue';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import VideoKanbanBoard from '@/components/Videos/VideoKanbanBoard.vue';
import Videos, { IRecordedProgram } from '@/services/Videos';

// カンバン表示用：全録画番組（最大 150 件・新しい順）
const allPrograms = ref<IRecordedProgram[]>([]);
const isLoading = ref(true);
const autoRefreshInterval = ref<number | null>(null);
const AUTO_REFRESH_INTERVAL = 30 * 1000;
const PAGE_LIMIT = 5;

// 録画番組を最大 5 ページ分まとめて取得する
const fetchAllPrograms = async () => {
    const results = await Promise.all(
        Array.from({ length: PAGE_LIMIT }, (_, i) => Videos.fetchVideos('desc', i + 1)),
    );
    const merged: IRecordedProgram[] = [];
    for (const result of results) {
        if (!result) break;
        merged.push(...result.recorded_programs);
        // 最終ページに到達したら打ち切る
        if (result.recorded_programs.length < result.total / PAGE_LIMIT) break;
    }
    allPrograms.value = merged;
    isLoading.value = false;
};

const startAutoRefresh = () => {
    if (autoRefreshInterval.value !== null) return;
    fetchAllPrograms();
    autoRefreshInterval.value = window.setInterval(fetchAllPrograms, AUTO_REFRESH_INTERVAL);
};

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

.video-week-kanban-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
    min-width: 0;
}

.video-week-kanban-container {
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

.video-week-kanban-header {
    display: flex;
    align-items: center;
    padding-bottom: 16px;
    @include smartphone-vertical {
        padding: 0px 8px 12px;
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

    // スマホ縦画面のみ表示する戻るボタン
    &__back {
        display: none;
        position: absolute;
        left: -8px;
        padding: 6px;
        border-radius: 50%;
        cursor: pointer;
        @include smartphone-vertical {
            display: flex;
        }

        & ~ span {
            @include smartphone-vertical {
                margin-left: 32px;
            }
        }
    }

    &__count {
        display: flex;
        align-items: center;
        padding-top: 8px;
        margin-left: 12px;
        font-size: 14px;
        font-weight: 400;
        color: rgb(var(--v-theme-text-darken-1));

        &-spin {
            animation: spin 1.15s linear infinite;
        }
        @keyframes spin {
            from { transform: rotate(0deg); }
            to   { transform: rotate(360deg); }
        }
    }
}

</style>
