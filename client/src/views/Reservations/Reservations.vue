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

                    <!-- 水平分割レイアウト：左=カンバン / 右=リスト -->
                    <div class="reservations-all-container__split">

                        <!-- 左パネル：週間カンバンボード -->
                        <div class="reservations-all-container__kanban-panel">
                            <h2 class="reservations-all-container__panel-title">
                                週間カレンダー
                            </h2>
                            <ReservationKanbanBoard
                                :reservations="allReservations"
                                :isLoading="isLoading"
                                @clickReservation="openDetail" />
                        </div>

                        <!-- 区切り線 -->
                        <div class="reservations-all-container__divider"></div>

                        <!-- 右パネル：予約リスト -->
                        <div class="reservations-all-container__list-panel">
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

    // パネルタイトル（カンバン側の「週間カレンダー」ラベル）
    &__panel-title {
        font-size: 20px;
        font-weight: 700;
        padding-top: 4px;
        padding-bottom: 12px;
        @include smartphone-vertical {
            font-size: 18px;
            padding-bottom: 8px;
        }
    }

    // 水平分割レイアウト
    &__split {
        display: flex;
        flex-direction: row;
        align-items: flex-start;
        gap: 0;
        width: 100%;
        min-width: 0;

        // タブレット縦画面以下は縦積みに切り替える
        @include tablet-vertical {
            flex-direction: column;
        }
        @include smartphone-horizontal {
            flex-direction: column;
        }
        @include smartphone-vertical {
            flex-direction: column;
        }
    }

    // 左：カンバンパネル（画面の広い方をカンバンに割り当てる）
    &__kanban-panel {
        flex: 1 1 0;
        min-width: 0;
        padding-right: 20px;
        @include tablet-vertical {
            padding-right: 0;
            padding-bottom: 24px;
            width: 100%;
        }
        @include smartphone-horizontal {
            padding-right: 0;
            padding-bottom: 20px;
            width: 100%;
        }
        @include smartphone-vertical {
            padding-right: 0;
            padding-bottom: 20px;
            width: 100%;
        }
    }

    // 区切り線（縦方向）
    &__divider {
        flex: 0 0 1px;
        align-self: stretch;
        background: rgb(var(--v-theme-background-lighten-2));
        margin: 0 4px;
        @include tablet-vertical {
            display: none;
        }
        @include smartphone-horizontal {
            display: none;
        }
        @include smartphone-vertical {
            display: none;
        }
    }

    // 右：リストパネル（固定幅）
    &__list-panel {
        flex: 0 0 400px;
        min-width: 0;
        padding-left: 20px;
        @include desktop {
            flex: 0 0 420px;
        }
        @include tablet-horizontal {
            flex: 0 0 360px;
        }
        @include tablet-vertical {
            padding-left: 0;
            flex: unset;
            width: 100%;
        }
        @include smartphone-horizontal {
            padding-left: 0;
            flex: unset;
            width: 100%;
        }
        @include smartphone-vertical {
            padding-left: 0;
            flex: unset;
            width: 100%;
        }
    }
}

</style>
