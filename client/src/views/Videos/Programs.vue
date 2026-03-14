<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="recorded-programs-container-wrapper">
                <SPHeaderBar />
                <div class="recorded-programs-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: 'ビデオをみる', path: '/videos/' },
                        { name: '録画番組一覧', path: '/videos/programs', disabled: true },
                    ]" />
                    <div v-if="storage_info && storage_info.folders.length > 0" class="storage-bar-section">
                        <div v-for="folder in storage_info.folders" :key="folder.paths[0]" class="storage-bar">
                            <div class="storage-bar__header">
                                <span class="storage-bar__label">
                                    <Icon icon="fluent:storage-20-regular" width="15px" class="mr-1" />
                                    {{ folder.paths.join('  /  ') }}
                                </span>
                                <span class="storage-bar__usage">
                                    {{ formatBytes(folder.used_bytes) }} / {{ formatBytes(folder.total_bytes) }} ({{ Math.round(folder.used_bytes / folder.total_bytes * 100) }}%)
                                </span>
                            </div>
                            <v-progress-linear
                                :model-value="folder.used_bytes / folder.total_bytes * 100"
                                :color="storageUsageColor(folder.used_bytes / folder.total_bytes)"
                                bg-color="background-lighten-2"
                                rounded
                                height="5" />
                        </div>
                    </div>
                    <RecordedProgramList
                        title="録画番組一覧"
                        :programs="programs"
                        :total="total_programs"
                        :page="current_page"
                        :sortOrder="sort_order"
                        :isLoading="is_loading"
                        :showBackButton="true"
                        :showEmptyMessage="!is_loading"
                        @update:page="updatePage"
                        @update:sortOrder="updateSortOrder($event as SortOrder)" />
                </div>
            </div>
        </main>
    </div>
</template>
<script lang="ts" setup>

import { onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import RecordedProgramList from '@/components/Videos/RecordedProgramList.vue';
import { IRecordedProgram, IStorageInfo, SortOrder } from '@/services/Videos';
import Videos from '@/services/Videos';
import useUserStore from '@/stores/UserStore';

// ルーター
const route = useRoute();
const router = useRouter();

// 録画番組のリスト
const programs = ref<IRecordedProgram[]>([]);
const total_programs = ref(0);
const is_loading = ref(true);

// ストレージ情報
const storage_info = ref<IStorageInfo | null>(null);

// 現在のページ番号
const current_page = ref(1);

// 並び順
const sort_order = ref<'desc' | 'asc'>('desc');

// バイト数を人間が読みやすい形式 (GB / MB) に変換する
const formatBytes = (bytes: number): string => {
    if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(1) + ' GB';
    return (bytes / 1024 ** 2).toFixed(0) + ' MB';
};

// ストレージ使用率に応じた色を返す (90%以上: エラー赤、75%以上: 警告黄、それ以下: プライマリ)
const storageUsageColor = (ratio: number): string => {
    if (ratio >= 0.9) return 'error';
    if (ratio >= 0.75) return 'warning';
    return 'primary';
};

// 録画番組を取得
const fetchPrograms = async () => {
    const result = await Videos.fetchVideos(sort_order.value, current_page.value);
    if (result) {
        programs.value = result.recorded_programs;
        total_programs.value = result.total;
    }
    is_loading.value = false;
};

// ページを更新
const updatePage = async (page: number) => {
    current_page.value = page;
    is_loading.value = true;
    await router.replace({
        query: {
            ...route.query,
            page: page.toString(),
        },
    });
};

// 並び順を更新
const updateSortOrder = async (order: 'desc' | 'asc') => {
    sort_order.value = order;
    current_page.value = 1;  // ページを1に戻す
    is_loading.value = true;
    await router.replace({
        query: {
            ...route.query,
            order,
            page: '1',
        },
    });
};

// クエリパラメータが変更されたら録画番組を再取得
watch(() => route.query, async (newQuery) => {
    // ページ番号を同期
    if (newQuery.page) {
        current_page.value = parseInt(newQuery.page as string);
    }
    // ソート順を同期
    if (newQuery.order) {
        sort_order.value = newQuery.order as 'desc' | 'asc';
    }
    await fetchPrograms();
}, { deep: true });

// 開始時に実行
onMounted(async () => {
    // 事前にログイン状態を同期（トークンがあればユーザー情報を取得）
    const userStore = useUserStore();
    await userStore.fetchUser();

    // クエリパラメータから初期値を設定
    if (route.query.page) {
        current_page.value = parseInt(route.query.page as string);
    }
    if (route.query.order) {
        sort_order.value = route.query.order as 'desc' | 'asc';
    }

    // 録画番組とストレージ情報を並行して取得
    const [, storage_result] = await Promise.all([
        fetchPrograms(),
        Videos.fetchStorageInfo(),
    ]);
    storage_info.value = storage_result;
});

</script>
<style lang="scss" scoped>

.recorded-programs-container-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
}

.recorded-programs-container {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    padding: 20px;
    margin: 0 auto;
    min-width: 0;
    max-width: 1000px;
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

.storage-bar-section {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 12px;
}

.storage-bar {
    display: flex;
    flex-direction: column;
    gap: 5px;
    &__header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        font-size: 0.82rem;
        color: rgb(var(--v-theme-text-darken-1));
    }
    &__label {
        display: flex;
        align-items: center;
        min-width: 0;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
    }
    &__usage {
        flex-shrink: 0;
        font-variant-numeric: tabular-nums;
    }
}

</style>