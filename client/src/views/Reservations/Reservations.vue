<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="reservations-all-container-wrapper">
                <SPHeaderBar />
                <div class="reservations-all-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: '録画予約', path: '/reservations/' },
                        { name: '録画予約一覧', path: '/reservations/all', disabled: true },
                    ]" />

                    <!-- 自動予約ルールへのリンクカード -->
                    <v-card class="reservations-all-container__rule-card mb-4" elevation="1"
                        @click="$router.push('/reservations/conditions')" style="cursor: pointer;">
                        <v-card-text class="reservations-all-container__rule-card-content">
                            <Icon icon="fluent:tag-20-regular" width="26px"
                                class="reservations-all-container__rule-card-icon" />
                            <div class="reservations-all-container__rule-card-text">
                                <div class="reservations-all-container__rule-card-title">自動予約ルール</div>
                                <div class="reservations-all-container__rule-card-sub">
                                    キーワードを指定して番組を自動的に録画予約するルールを管理します。
                                </div>
                            </div>
                            <Icon icon="fluent:chevron-right-20-regular" width="20px"
                                class="reservations-all-container__rule-card-arrow" />
                        </v-card-text>
                    </v-card>

                    <!-- 週間カンバンボード -->
                    <h2 class="reservations-all-container__section-title">週間カレンダー</h2>
                    <ReservationKanbanBoard
                        class="mb-6"
                        :reservations="allReservations"
                        :isLoading="isLoading"
                        @clickReservation="openDetail" />

                    <!-- 区切り線 -->
                    <div class="reservations-all-container__divider"></div>

                    <!-- 予約リスト -->
                    <ReservationList ref="reservationList"
                        title="録画予約一覧"
                        :reservations="reservations"
                        :total="total"
                        :page="page"
                        :sort-order="sortOrder"
                        :is-loading="isLoading"
                        :show-back-button="false"
                        :show-empty-message="!isLoading"
                        @update:page="updatePage"
                        @update:sort-order="updateSortOrder"
                        @delete="handleReservationDeleted">
                    </ReservationList>
                </div>
            </div>
        </main>

        <!-- 録画予約詳細ドロワー（カンバンカードクリック時に使用） -->
        <ReservationDetailDrawer
            v-model="drawerOpen"
            :reservation="selectedReservation"
            @deleted="handleDrawerDeleted"
            @updated="handleDrawerUpdated" />
    </div>
</template>
<script lang="ts" setup>

import { ref, onMounted, watch, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import ReservationDetailDrawer from '@/components/Reservations/ReservationDetailDrawer.vue';
import ReservationKanbanBoard from '@/components/Reservations/ReservationKanbanBoard.vue';
import ReservationList from '@/components/Reservations/ReservationList.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import Reservations, { IReservation } from '@/services/Reservations';

const route = useRoute();
const router = useRouter();

// 全録画予約（カンバンとリストで共有）
const allReservations = ref<IReservation[]>([]);

// リスト表示用（ソート・ページング後）
const reservations = ref<IReservation[]>([]);
const total = ref<number>(0);
const page = ref<number>(1);
const sortOrder = ref<'desc' | 'asc'>('asc');
const isLoading = ref<boolean>(true);

// カンバンカードクリック時の詳細ドロワー
const drawerOpen = ref(false);
const selectedReservation = ref<IReservation | null>(null);

const reservationList = ref<InstanceType<typeof ReservationList>>();

const autoRefreshInterval = ref<number | null>(null);
const AUTO_REFRESH_INTERVAL = 30 * 1000;
const ITEMS_PER_PAGE = 25;

/**
 * 録画予約一覧を取得する
 */
async function fetchAllReservations() {
    const result = await Reservations.fetchReservations();
    if (result) {
        allReservations.value = result.reservations;
    }
}

/**
 * 表示用データを計算する（クライアント側ソート・ページング）
 */
function updateDisplayData() {
    if (allReservations.value.length === 0) {
        reservations.value = [];
        total.value = 0;
        return;
    }

    // 並び順に応じてソート
    let sortedReservations = [...allReservations.value];
    if (sortOrder.value === 'asc') {
        sortedReservations.sort((a, b) => new Date(a.program.start_time).getTime() - new Date(b.program.start_time).getTime());
    } else {
        sortedReservations.sort((a, b) => new Date(b.program.start_time).getTime() - new Date(a.program.start_time).getTime());
    }

    const startIndex = (page.value - 1) * ITEMS_PER_PAGE;
    reservations.value = sortedReservations.slice(startIndex, startIndex + ITEMS_PER_PAGE);
    total.value = sortedReservations.length;
}

async function updatePage(new_page: number) {
    page.value = new_page;
    await router.replace({ query: { ...route.query, page: new_page.toString() } });
}

async function updateSortOrder(new_sort_order: 'desc' | 'asc') {
    sortOrder.value = new_sort_order;
    page.value = 1;
    await router.replace({ query: { ...route.query, order: new_sort_order, page: '1' } });
}

/**
 * リストパネルからの削除イベント処理
 */
function handleReservationDeleted(reservation_id: number) {
    allReservations.value = allReservations.value.filter(r => r.id !== reservation_id);
    updateDisplayData();
    updateAllSections();
}

/**
 * カンバンカードクリック時：詳細ドロワーを開く
 */
function openDetail(reservation: IReservation) {
    selectedReservation.value = reservation;
    drawerOpen.value = true;
}

/**
 * カンバンドロワーからの削除イベント処理
 */
function handleDrawerDeleted(reservation_id: number) {
    allReservations.value = allReservations.value.filter(r => r.id !== reservation_id);
    updateDisplayData();
    drawerOpen.value = false;
    updateAllSections();
}

/**
 * カンバンドロワーからの更新イベント処理
 */
function handleDrawerUpdated(updated: IReservation) {
    const idx = allReservations.value.findIndex(r => r.id === updated.id);
    if (idx !== -1) {
        allReservations.value[idx] = updated;
        updateDisplayData();
    }
    selectedReservation.value = updated;
}

const updateAllSections = async () => {
    try {
        await fetchAllReservations();
        isLoading.value = false;
    } catch (error) {
        console.error('Failed to update reservation list:', error);
        isLoading.value = false;
    }
};

const startAutoRefresh = () => {
    if (autoRefreshInterval.value === null) {
        updateAllSections();
        autoRefreshInterval.value = window.setInterval(updateAllSections, AUTO_REFRESH_INTERVAL);
    }
};

const stopAutoRefresh = () => {
    if (autoRefreshInterval.value !== null) {
        clearInterval(autoRefreshInterval.value);
        autoRefreshInterval.value = null;
    }
};

// クエリパラメータ変更時に表示データを更新
watch(() => route.query, (newQuery) => {
    if (newQuery.page) {
        const p = parseInt(String(newQuery.page), 10);
        if (Number.isFinite(p) && p > 0) page.value = p;
    }
    if (newQuery.order) {
        const o = String(newQuery.order);
        if (o === 'asc' || o === 'desc') sortOrder.value = o;
    }
    updateDisplayData();
}, { deep: true });

// allReservations 変更時にリスト表示データを更新
watch(() => allReservations.value, () => { updateDisplayData(); }, { deep: true });

onMounted(async () => {
    if (route.query.page && typeof route.query.page === 'string') {
        page.value = parseInt(route.query.page, 10);
    }
    if (route.query.order && typeof route.query.order === 'string') {
        sortOrder.value = route.query.order as 'desc' | 'asc';
    }
    startAutoRefresh();
});

onUnmounted(() => { stopAutoRefresh(); });

</script>
<style lang="scss" scoped>

.reservations-all-container-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
    min-width: 0;
}

.reservations-all-container {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    padding: 20px;
    margin: 0 auto;
    max-width: 1200px;
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

    // 自動予約ルールリンクカード
    &__rule-card {
        background: rgb(var(--v-theme-background-lighten-2)) !important;

        &-content {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 12px 16px !important;
        }

        &-icon {
            flex-shrink: 0;
            color: rgb(var(--v-theme-primary));
        }

        &-text {
            flex: 1;
            min-width: 0;
        }

        &-title {
            font-size: 0.9rem;
            font-weight: bold;
        }

        &-sub {
            font-size: 0.78rem;
            color: rgb(var(--v-theme-text-darken-1));
            margin-top: 2px;
        }

        &-arrow {
            flex-shrink: 0;
            color: rgb(var(--v-theme-text-darken-1));
        }
    }

    // セクションタイトル（週間カレンダー）
    &__section-title {
        font-size: 20px;
        font-weight: 700;
        padding-top: 4px;
        padding-bottom: 12px;
        @include smartphone-vertical {
            font-size: 18px;
            padding-bottom: 8px;
            padding-left: 8px;
        }
    }

    // カンバンとリストの間の水平区切り線
    &__divider {
        width: 100%;
        height: 1px;
        background: rgb(var(--v-theme-background-lighten-2));
        margin: 4px 0 28px;
        @include smartphone-vertical {
            margin: 4px 0 20px;
        }
    }
}

</style>
