<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="videos-home-container-wrapper">
                <SPHeaderBar />
                <div class="videos-home-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: 'ビデオをみる', path: '/videos/', disabled: true },
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
                    <!-- 追っかけ再生 (録画中の番組があるときのみ表示) -->
                    <RecordedProgramList
                        v-if="recording_programs.length > 0"
                        class="videos-home-container__recording-programs"
                        title="追っかけ再生"
                        :programs="recording_programs"
                        :total="total_recording_programs"
                        :hideSort="true"
                        :hidePagination="true"
                        :showMoreButton="true"
                        :isLoading="is_loading"
                        :showEmptyMessage="false"
                        @more="$router.push('/videos/recording')" />
                    <RecordedProgramList
                        class="videos-home-container__recent-programs"
                        :class="{'videos-home-container__recent-programs--loading': recent_programs.length === 0 && is_loading}"
                        title="新着の録画番組"
                        :programs="recent_programs"
                        :total="total_programs"
                        :hideSort="true"
                        :hidePagination="true"
                        :showMoreButton="true"
                        :showSearch="true"
                        :isLoading="is_loading"
                        :showEmptyMessage="!is_loading"
                        @more="$router.push('/videos/programs')" />
                    <!-- シリーズ一覧 -->
                    <div class="series-section">
                        <div class="series-section__header">
                            <h2 class="series-section__title">
                                <span class="series-section__title-text">シリーズ</span>
                            </h2>
                            <div class="series-section__actions">
                                <v-btn variant="text" class="series-section__more"
                                    @click="$router.push('/videos/series')">
                                    <span class="text-primary">もっと見る</span>
                                    <Icon icon="fluent:chevron-right-12-regular" width="18px"
                                        class="ml-1 text-text-darken-1" style="margin: 0px -4px;" />
                                </v-btn>
                            </div>
                        </div>
                        <div class="series-section__grid">
                            <!-- シリーズが存在する場合: カードリスト表示 -->
                            <div class="series-section__grid-content" v-if="recent_series.length > 0">
                                <router-link class="series-section__card" v-for="s in recent_series" :key="s.id"
                                    :to="`/videos/series/${s.id}`">
                                    <div class="series-section__card-thumbnail">
                                        <img v-if="getLatestProgram(s)" loading="lazy"
                                            :src="`${Utils.api_base_url}/videos/${getLatestProgram(s)!.id}/thumbnail`" />
                                        <span class="series-section__card-badge">
                                            {{ getTotalEpisodeCount(s) }}件
                                        </span>
                                    </div>
                                    <div class="series-section__card-content">
                                        <span class="series-section__card-title">{{ s.title }}</span>
                                        <div class="series-section__card-meta">
                                            <span class="series-section__card-channel" v-if="getLatestPeriod(s)">
                                                {{ getLatestPeriod(s)!.channel.name }}
                                            </span>
                                            <span class="series-section__card-genres" v-if="s.genres.length > 0">
                                                {{ s.genres.map(g => g.major).join(' / ') }}
                                            </span>
                                        </div>
                                    </div>
                                </router-link>
                            </div>
                            <!-- シリーズが存在しない場合: 空状態メッセージ -->
                            <div class="series-section__empty" v-else-if="!is_loading">
                                <div class="series-section__empty-content">
                                    <Icon class="series-section__empty-icon" icon="fluent:video-clip-multiple-16-regular"
                                        width="54px" height="54px" />
                                    <h2>シリーズ番組がまだありません。</h2>
                                    <div class="series-section__empty-sub">
                                        録画番組のスキャン完了後に<br class="d-sm-none">自動的に表示されます。
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <RecordedProgramList
                        title="マイリスト"
                        :programs="mylist_programs"
                        :total="total_mylist_programs"
                        :hideSort="true"
                        :hidePagination="true"
                        :showMoreButton="true"
                        :showEmptyMessage="!is_loading"
                        :emptyIcon="'ic:round-playlist-play'"
                        :emptyMessage="['あとで観たい番組を', 'マイリストに保存できます。']"
                        :emptySubMessage="['録画番組の右上にある ＋ ボタンから、', '番組をマイリストに追加できます。']"
                        :isLoading="is_loading"
                        :forMylist="true"
                        @more="$router.push('/mylist/')" />
                    <RecordedProgramList
                        title="視聴履歴"
                        :programs="watched_programs"
                        :total="total_watched_programs"
                        :hideSort="true"
                        :hidePagination="true"
                        :showMoreButton="true"
                        :showEmptyMessage="!is_loading"
                        :emptyIcon="'fluent:history-20-regular'"
                        :emptyMessage="'まだ視聴履歴がありません。'"
                        :emptySubMessage="['録画番組を30秒以上みると、', '視聴履歴に追加されます。']"
                        :isLoading="is_loading"
                        :forWatchedHistory="true"
                        @more="$router.push('/watched-history/')" />
                </div>
            </div>
        </main>
    </div>
</template>
<script lang="ts" setup>

import { onMounted, ref, onUnmounted, watch } from 'vue';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import RecordedProgramList from '@/components/Videos/RecordedProgramList.vue';
import SeriesService, { ISeries } from '@/services/Series';
import { IRecordedProgram, IStorageInfo, isChasePlaybackProgram } from '@/services/Videos';
import Videos from '@/services/Videos';
import useSettingsStore from '@/stores/SettingsStore';
import useUserStore from '@/stores/UserStore';
import Utils from '@/utils';

// ストレージ情報
const storage_info = ref<IStorageInfo | null>(null);

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

// 最近録画された番組のリスト
const recent_programs = ref<IRecordedProgram[]>([]);
const total_programs = ref(0);

// シリーズのリスト
const recent_series = ref<ISeries[]>([]);
const total_series = ref(0);

// マイリストの録画番組のリスト
const mylist_programs = ref<IRecordedProgram[]>([]);
const total_mylist_programs = ref(0);

// 視聴履歴の録画番組のリスト
const watched_programs = ref<IRecordedProgram[]>([]);
const total_watched_programs = ref(0);

// 追っかけ再生できる録画中番組のリスト
const recording_programs = ref<IRecordedProgram[]>([]);
const total_recording_programs = ref(0);

const is_loading = ref(true);

// 自動更新用の interval ID を保持
const autoRefreshInterval = ref<number | null>(null);

// 自動更新の間隔 (ミリ秒)
// 解析中の番組がある場合は短い間隔でポーリングし、解析完了を素早く検出する
const AUTO_REFRESH_INTERVAL = 30 * 1000;         // 30秒 (通常)
const ANALYZING_REFRESH_INTERVAL = 5 * 1000;     // 5秒  (解析中の番組がある場合)

// マイリストの変更を監視して即座に再取得
const settingsStore = useSettingsStore();
watch(() => settingsStore.settings.mylist, async () => {
    await fetchMylistPrograms();
}, { deep: true });

// 視聴履歴の変更を監視して即座に再取得
watch(() => settingsStore.settings.watched_history, async () => {
    await fetchWatchedPrograms();
}, { deep: true });

// 最近録画された番組を取得
const fetchRecentPrograms = async () => {
    const result = await Videos.fetchVideos('desc', 1);
    if (result) {
        recent_programs.value = result.recorded_programs.slice(0, 10);  // 最新10件のみ表示
        total_programs.value = result.total;
    }
};

// 追っかけ再生できる録画中番組を取得
const fetchRecordingPrograms = async () => {
    // 録画中の番組のみをサーバー側で絞り込んで取得する (総数も録画中のものだけの正確な件数になる)
    const result = await Videos.fetchVideos('desc', 1, null, null, null, 'Recording');
    if (result) {
        // 録画終了時刻を大きく過ぎても status が Recording のまま残っている録画は、追っかけ再生できないため除外する
        recording_programs.value = result.recorded_programs.filter(isChasePlaybackProgram).slice(0, 10);  // 最新10件のみ表示
        total_recording_programs.value = result.total;
    }
};

// シリーズ一覧を取得 (最新4件)
const fetchRecentSeries = async () => {
    const result = await SeriesService.fetchSeriesList('desc', 1);
    if (result) {
        recent_series.value = result.series_list.slice(0, 4);
        total_series.value = result.total;
    }
};

// シリーズの最新放送期間を取得する
const getLatestPeriod = (s: ISeries) => {
    if (s.broadcast_periods.length === 0) return null;
    return s.broadcast_periods[s.broadcast_periods.length - 1];
};

// シリーズの最新エピソード (サムネイル用) を取得する
const getLatestProgram = (s: ISeries) => {
    const period = getLatestPeriod(s);
    if (!period || period.recorded_programs.length === 0) return null;
    return period.recorded_programs[period.recorded_programs.length - 1];
};

// シリーズの全エピソード数を算出する
const getTotalEpisodeCount = (s: ISeries): number => {
    return s.broadcast_periods.reduce(
        (sum, period) => sum + period.recorded_programs.length, 0,
    );
};

// マイリストの録画番組を取得
const fetchMylistPrograms = async () => {
    // マイリストに登録されている録画番組の ID を取得
    const mylist_ids = settingsStore.settings.mylist
        .filter(item => item.type === 'RecordedProgram')
        .sort((a, b) => b.created_at - a.created_at)  // 新しい順
        .map(item => item.id);

    // マイリストが空の場合は早期リターン
    if (mylist_ids.length === 0) {
        mylist_programs.value = [];
        total_mylist_programs.value = 0;
        return;
    }

    // 録画番組を取得
    const result = await Videos.fetchVideos('ids', 1, mylist_ids);
    if (result) {
        mylist_programs.value = result.recorded_programs.slice(0, 4);  // 最新4件のみ表示
        total_mylist_programs.value = result.total;
    }
};

// 視聴履歴の録画番組を取得
const fetchWatchedPrograms = async () => {
    // 視聴履歴に登録されている録画番組の ID を取得
    const watched_ids = settingsStore.settings.watched_history
        .sort((a, b) => b.updated_at - a.updated_at)  // 最後に視聴した順
        .map(history => history.video_id);

    // 視聴履歴が空の場合は早期リターン
    if (watched_ids.length === 0) {
        watched_programs.value = [];
        total_watched_programs.value = 0;
        return;
    }

    // 録画番組を取得
    const result = await Videos.fetchVideos('ids', 1, watched_ids);
    if (result) {
        watched_programs.value = result.recorded_programs.slice(0, 4);  // 最新4件のみ表示
        total_watched_programs.value = result.total;
    }
};

// 各セクションの更新関数を管理するオブジェクト
const sectionUpdaters = {
    recordingPrograms: fetchRecordingPrograms,
    recentPrograms: fetchRecentPrograms,
    recentSeries: fetchRecentSeries,
    mylistPrograms: fetchMylistPrograms,
    watchedPrograms: fetchWatchedPrograms,
} as const;

// 現在表示中のいずれかの番組がバックグラウンド解析中かどうかを返す
// thumbnail_info が null かつ AnalysisFailed でない場合、サムネイル生成などのバックグラウンド解析がまだ完了していない
// なお録画中の番組は録画が終わるまでサムネイルが生成されないため、ここには意図的に含めていない
// 含めてしまうと、録画が続いている間ずっと短い間隔でのポーリングが解除されなくなる
const hasAnalyzingPrograms = () => {
    const allPrograms = [
        ...recent_programs.value,
        ...mylist_programs.value,
        ...watched_programs.value,
    ];
    return allPrograms.some(
        p => p.recorded_video.thumbnail_info === null && p.recorded_video.status !== 'AnalysisFailed',
    );
};

// 全セクションの更新を実行
const updateAllSections = async () => {
    try {
        // 全セクションの更新関数とストレージ情報の取得を並行実行
        const results = await Promise.all([
            ...Object.values(sectionUpdaters).map(updater => updater()),
            Videos.fetchStorageInfo(),
        ]);
        // fetchStorageInfo の結果は配列の最後の要素
        storage_info.value = results[results.length - 1] as IStorageInfo | null;
        is_loading.value = false;
    } catch (error) {
        console.error('Failed to update sections:', error);
        is_loading.value = false;
    }

    // 解析中の番組がある場合は短い間隔でポーリングし解析完了を素早く検出する。
    // ない場合は通常間隔に戻す。interval が変わる場合のみ再設定する。
    if (autoRefreshInterval.value !== null) {
        const nextInterval = hasAnalyzingPrograms() ? ANALYZING_REFRESH_INTERVAL : AUTO_REFRESH_INTERVAL;
        clearInterval(autoRefreshInterval.value);
        autoRefreshInterval.value = window.setInterval(updateAllSections, nextInterval);
    }
};

// 自動更新を開始
const startAutoRefresh = () => {
    if (autoRefreshInterval.value === null) {
        // 初回更新
        updateAllSections();
        // 定期更新を開始 (updateAllSections 内で解析状態に応じて間隔を再設定する)
        autoRefreshInterval.value = window.setInterval(updateAllSections, AUTO_REFRESH_INTERVAL);
    }
};

// 自動更新を停止
const stopAutoRefresh = () => {
    if (autoRefreshInterval.value !== null) {
        clearInterval(autoRefreshInterval.value);
        autoRefreshInterval.value = null;
    }
};

// 開始時に実行
onMounted(async () => {
    // 事前にログイン状態を同期（トークンがあればユーザー情報を取得）
    const userStore = useUserStore();
    await userStore.fetchUser();
    startAutoRefresh();
});

// コンポーネントのクリーンアップ
onUnmounted(() => {
    stopAutoRefresh();
});

</script>
<style lang="scss" scoped>

.videos-home-container-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
    min-width: 0;  // サイドナビゲーション横のフレックス子要素を親幅内で縮め、タブレット縦画面でのはみ出しを防ぐ
}

.videos-home-container {
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

    :deep(.recorded-program-list) {
        & + .recorded-program-list {
            margin-top: 28px;
            @include smartphone-vertical {
                margin-top: 16px;
            }
        }
    }

    &__recent-programs.videos-home-container__recent-programs--loading {
        // ローディング中にちらつかないように
        :deep(.recorded-program-list__grid) {
            height: calc(125px * 10);
            @include smartphone-vertical {
                height: calc(100px * 10);
            }
        }
    }
}

.storage-bar-section {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
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

// シリーズセクション (RecordedProgramList のヘッダーパターンに準拠)
.series-section {
    margin-top: 28px;
    @include smartphone-vertical {
        margin-top: 16px;
    }

    &__header {
        display: flex;
        align-items: center;
        @include smartphone-vertical {
            padding: 0px 8px;
        }
    }

    &__title {
        display: flex;
        align-items: center;
        position: relative;
        font-size: 24px;
        font-weight: 700;
        padding-top: 8px;
        padding-bottom: 20px;
        @include smartphone-vertical {
            font-size: 22px;
            padding-bottom: 16px;
        }
    }

    &__actions {
        display: flex;
        align-items: center;
        margin-left: auto;
    }

    &__more {
        margin-bottom: 12px;
        padding: 0px 10px;
        font-size: 15px;
        letter-spacing: 0.05em;
        @include smartphone-vertical {
            margin-bottom: 6px;
        }
    }

    // シリーズカードグリッド (RecordedProgramList の __grid パターンに準拠)
    &__grid {
        display: flex;
        flex-direction: column;
        position: relative;
        width: 100%;
        min-height: 200px;
        background: rgb(var(--v-theme-background-lighten-1));
        border-radius: 8px;
        overflow: hidden;
    }

    &__grid-content {
        display: flex;
        flex-direction: column;
        height: 100%;
    }

    // シリーズカード (Series.vue の横長カードと同じパターン)
    &__card {
        display: flex;
        width: 100%;
        height: 125px;
        padding: 0px 16px;
        text-decoration: none;
        color: rgb(var(--v-theme-text));
        cursor: pointer;
        transition: background-color 0.15s ease;
        @include smartphone-vertical {
            height: auto;
            padding: 0px 9px;
        }

        &:hover {
            background-color: rgb(var(--v-theme-background-lighten-2));
        }

        & + .series-section__card {
            border-top: 1px solid rgb(var(--v-theme-background));
        }
    }

    &__card-thumbnail {
        position: relative;
        flex-shrink: 0;
        width: 178px;
        aspect-ratio: 16 / 9;
        margin: 12px 0;
        border-radius: 5px;
        overflow: hidden;
        background: linear-gradient(150deg, rgb(var(--v-theme-gray)), rgb(var(--v-theme-background-lighten-2)));
        @include smartphone-vertical {
            width: 130px;
            margin: 9px 0;
        }

        img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
    }

    &__card-badge {
        position: absolute;
        bottom: 4px;
        right: 4px;
        padding: 2px 6px;
        border-radius: 4px;
        background: rgba(0, 0, 0, 0.75);
        color: #ffffff;
        font-size: 11.5px;
        font-weight: 600;
    }

    &__card-content {
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 4px;
        padding: 12px 14px;
        min-width: 0;
        flex: 1;
        @include smartphone-vertical {
            padding: 9px 10px;
        }
    }

    &__card-title {
        font-size: 15px;
        font-weight: bold;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        @include smartphone-vertical {
            font-size: 14px;
            white-space: normal;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }
    }

    &__card-meta {
        display: flex;
        gap: 8px;
        font-size: 12.5px;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__card-channel {
        font-weight: 500;
    }

    // シリーズが0件の場合の空状態表示 (RecordedProgramList の __empty パターンに準拠)
    &__empty {
        display: flex;
        justify-content: center;
        align-items: center;
        width: 100%;
        height: 100%;
        padding-top: 28px;
        padding-bottom: 40px;
        flex-grow: 1;
        text-align: center;

        &-icon {
            color: rgb(var(--v-theme-text-darken-1));
        }

        h2 {
            font-size: 21px;
            @include smartphone-vertical {
                font-size: 19px !important;
                text-align: center;
            }
        }

        &-sub {
            margin-top: 8px;
            color: rgb(var(--v-theme-text-darken-1));
            font-size: 15px;
            @include smartphone-vertical {
                font-size: 13px !important;
                text-align: center;
                margin-top: 7px !important;
                line-height: 1.65;
            }
        }
    }
}

</style>
