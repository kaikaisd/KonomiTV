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

                    <!-- ページヘッダー：タイトル + 件数 -->
                    <div class="kanban-page-header">
                        <h2 class="kanban-page-header__title">
                            <div v-ripple class="kanban-page-header__back" @click="$router.back()">
                                <Icon icon="fluent:chevron-left-12-filled" width="27px" />
                            </div>
                            週間カレンダー
                            <span class="kanban-page-header__count">
                                <Icon v-if="isLoading" icon="line-md:loading-twotone-loop"
                                    class="kanban-page-header__count-spin" width="18px" height="18px" />
                                <template v-else>{{ allReservations.length }}件</template>
                            </span>
                        </h2>
                    </div>

                    <!-- カンバンボード本体（共有コンポーネント） -->
                    <ReservationKanbanBoard
                        :reservations="allReservations"
                        :isLoading="isLoading"
                        @clickReservation="openDetail" />
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

import { ref, onMounted, onUnmounted } from 'vue';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import ReservationDetailDrawer from '@/components/Reservations/ReservationDetailDrawer.vue';
import ReservationKanbanBoard from '@/components/Reservations/ReservationKanbanBoard.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import Reservations, { IReservation } from '@/services/Reservations';

const allReservations = ref<IReservation[]>([]);
const isLoading = ref(true);
const drawerOpen = ref(false);
const selectedReservation = ref<IReservation | null>(null);
const autoRefreshInterval = ref<number | null>(null);
const AUTO_REFRESH_INTERVAL = 30 * 1000;

const openDetail = (res: IReservation) => {
    selectedReservation.value = res;
    drawerOpen.value = true;
};

const handleDeleted = (id: number) => {
    allReservations.value = allReservations.value.filter(r => r.id !== id);
    drawerOpen.value = false;
};

const handleUpdated = (updated: IReservation) => {
    const idx = allReservations.value.findIndex(r => r.id === updated.id);
    if (idx !== -1) allReservations.value[idx] = updated;
    selectedReservation.value = updated;
};

const fetchReservations = async () => {
    const result = await Reservations.fetchReservations();
    if (result) allReservations.value = result.reservations;
    isLoading.value = false;
};

const startAutoRefresh = () => {
    if (autoRefreshInterval.value !== null) return;
    fetchReservations();
    autoRefreshInterval.value = window.setInterval(fetchReservations, AUTO_REFRESH_INTERVAL);
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

.kanban-page-header {
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
