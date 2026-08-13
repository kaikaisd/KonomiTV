<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="recording-programs-container-wrapper">
                <SPHeaderBar />
                <div class="recording-programs-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: 'ビデオをみる', path: '/videos/' },
                        { name: '追っかけ再生', path: '/videos/recording', disabled: true },
                    ]" />
                    <RecordedProgramList
                        title="追っかけ再生"
                        :programs="programs"
                        :total="total_programs"
                        :page="current_page"
                        :hideSort="true"
                        :isLoading="is_loading"
                        :showBackButton="true"
                        :showEmptyMessage="!is_loading"
                        :emptyIcon="'fluent:video-clip-20-regular'"
                        :emptyMessage="'現在録画中の番組はありません。'"
                        :emptySubMessage="'録画中の番組は、ここから追っかけ再生できます。'"
                        @update:page="updatePage" />
                </div>
            </div>
        </main>
    </div>
</template>
<script lang="ts" setup>

import { onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import RecordedProgramList from '@/components/Videos/RecordedProgramList.vue';
import Videos, { type IRecordedProgram, isChasePlaybackProgram } from '@/services/Videos';
import useUserStore from '@/stores/UserStore';

// 録画中番組の一覧を再取得する間隔 (ミリ秒)
// 録画の開始・終了が一覧へ自然に反映されるよう、視聴中でなくても定期的に更新する
const REFRESH_INTERVAL_MS = 30 * 1000;

const route = useRoute();
const router = useRouter();

// 追っかけ再生できる録画中番組のリスト
const programs = ref<IRecordedProgram[]>([]);
const total_programs = ref(0);
const is_loading = ref(true);

// 現在のページ番号
const current_page = ref(1);

// 定期更新用のタイマー ID
let refresh_timer_id = 0;

// 追っかけ再生できる録画中番組を取得する
const fetchPrograms = async () => {
    // 録画中の番組のみをサーバー側で絞り込んで取得する
    // 全件取得してクライアント側で絞り込むと、録画数に比例して API リクエストが増えてしまうため
    const result = await Videos.fetchVideos('desc', current_page.value, null, null, null, 'Recording');
    if (result !== null) {
        // 録画終了時刻を大きく過ぎても status が Recording のまま残っている録画は、追っかけ再生できないため除外する
        programs.value = result.recorded_programs.filter(isChasePlaybackProgram);
        total_programs.value = result.total;
    }
    is_loading.value = false;
};

// ページを更新する
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

// クエリパラメータが変更されたら録画中番組を再取得する
watch(() => route.query, async (newQuery) => {
    if (newQuery.page) {
        current_page.value = parseInt(newQuery.page as string);
    }
    await fetchPrograms();
}, { deep: true });

// 開始時に実行
onMounted(async () => {
    const userStore = useUserStore();
    await userStore.fetchUser();

    if (route.query.page) {
        current_page.value = parseInt(route.query.page as string);
    }

    await fetchPrograms();

    // 録画の開始・終了を一覧へ反映するため、定期的に再取得する
    refresh_timer_id = window.setInterval(() => fetchPrograms(), REFRESH_INTERVAL_MS);
});

// 終了時に実行
onUnmounted(() => {
    window.clearInterval(refresh_timer_id);
});

</script>
<style lang="scss" scoped>

.recording-programs-container-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
    min-width: 0;  // サイドナビゲーション横のフレックス子要素を親幅内で縮め、タブレット縦画面でのはみ出しを防ぐ
}

.recording-programs-container {
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
        padding-top: 8px !important;
        padding-left: 8px !important;
        padding-right: 8px !important;
        padding-bottom: 20px !important;
    }
}

</style>
