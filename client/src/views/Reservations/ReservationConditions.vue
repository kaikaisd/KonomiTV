
<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="conditions-wrapper">
                <SPHeaderBar />
                <div class="conditions-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: '録画予約', path: '/reservations/' },
                        { name: '自動予約ルール', path: '/reservations/conditions', disabled: true },
                    ]" />

                    <!-- ヘッダー行 -->
                    <div class="conditions-container__header">
                        <div class="conditions-container__title">自動予約ルール一覧</div>
                        <v-btn color="primary" prepend-icon="fluent:add-20-regular" @click="openAddDialog">
                            ルールを追加
                        </v-btn>
                    </div>

                    <!-- ルールリスト -->
                    <div v-if="isLoading" class="conditions-container__loading">
                        <v-progress-circular indeterminate color="primary" />
                    </div>
                    <div v-else-if="conditions.length === 0" class="conditions-container__empty">
                        <Icon icon="fluent:tag-20-regular" width="64px"
                            class="conditions-container__empty-icon" />
                        <div class="conditions-container__empty-message">
                            自動予約ルールがまだありません。
                        </div>
                        <div class="conditions-container__empty-sub">
                            キーワードを指定してルールを追加すると、条件に一致する番組が自動的に予約されます。
                        </div>
                        <v-btn color="primary" prepend-icon="fluent:add-20-regular"
                            class="mt-4" @click="openAddDialog">
                            最初のルールを追加
                        </v-btn>
                    </div>
                    <div v-else class="conditions-container__list">
                        <v-card v-for="condition in conditions" :key="condition.id"
                            class="condition-card mb-3" elevation="1">
                            <v-card-text class="condition-card__content">
                                <!-- 左側: ステータスバッジ + メイン情報 -->
                                <div class="condition-card__main">
                                    <div class="condition-card__header-row">
                                        <!-- 有効/無効バッジ -->
                                        <v-chip
                                            :color="condition.program_search_condition.is_enabled ? 'success' : 'default'"
                                            size="small" class="condition-card__badge">
                                            {{ condition.program_search_condition.is_enabled ? '有効' : '無効' }}
                                        </v-chip>
                                        <!-- ID -->
                                        <span class="condition-card__id">ID: {{ condition.id }}</span>
                                        <!-- 予約数 -->
                                        <v-chip color="primary" variant="tonal" size="small">
                                            <Icon icon="fluent:timer-16-regular" width="14px" class="mr-1" />
                                            {{ condition.reservation_count }} 件の予約
                                        </v-chip>
                                    </div>
                                    <!-- キーワード -->
                                    <div class="condition-card__keyword">
                                        <Icon icon="fluent:search-20-regular" width="16px"
                                            class="condition-card__keyword-icon" />
                                        <span v-if="condition.program_search_condition.keyword">
                                            {{ condition.program_search_condition.keyword }}
                                        </span>
                                        <span v-else class="condition-card__keyword--empty">
                                            (キーワード指定なし・全番組対象)
                                        </span>
                                    </div>
                                    <!-- メモ -->
                                    <div v-if="condition.program_search_condition.note"
                                        class="condition-card__note">
                                        <Icon icon="fluent:note-20-regular" width="14px"
                                            class="condition-card__note-icon" />
                                        {{ condition.program_search_condition.note }}
                                    </div>
                                    <!-- 検索条件サマリ -->
                                    <div class="condition-card__tags">
                                        <v-chip v-if="condition.program_search_condition.is_title_only"
                                            size="x-small" variant="outlined">番組名のみ</v-chip>
                                        <v-chip v-if="condition.program_search_condition.is_regex_search_enabled"
                                            size="x-small" variant="outlined">正規表現</v-chip>
                                        <v-chip v-if="condition.program_search_condition.broadcast_type !== 'All'"
                                            size="x-small" variant="outlined">
                                            {{ condition.program_search_condition.broadcast_type === 'FreeOnly' ? '無料のみ' : '有料のみ' }}
                                        </v-chip>
                                        <v-chip v-if="condition.program_search_condition.duplicate_title_check_scope !== 'None'"
                                            size="x-small" variant="outlined">重複チェック</v-chip>
                                    </div>
                                </div>
                                <!-- 右側: 操作ボタン -->
                                <div class="condition-card__actions">
                                    <v-btn icon variant="text" size="small"
                                        v-ftooltip.top="'編集'"
                                        @click="openEditDialog(condition)">
                                        <Icon icon="fluent:edit-20-regular" width="20px" />
                                    </v-btn>
                                    <v-btn icon variant="text" size="small" color="error"
                                        v-ftooltip.top="'削除'"
                                        @click="confirmDelete(condition)">
                                        <Icon icon="fluent:delete-20-regular" width="20px" />
                                    </v-btn>
                                </div>
                            </v-card-text>
                        </v-card>
                    </div>
                </div>
            </div>
        </main>

        <!-- 追加/編集ダイアログ -->
        <ReservationConditionEditDialog
            v-model="isEditDialogOpen"
            :condition="editingCondition"
            @saved="onSaved" />

        <!-- 削除確認ダイアログ -->
        <v-dialog v-model="isDeleteDialogOpen" max-width="420px">
            <v-card>
                <v-card-title>ルールを削除しますか？</v-card-title>
                <v-card-text>
                    <span v-if="deletingCondition?.program_search_condition.keyword">
                        キーワード「{{ deletingCondition.program_search_condition.keyword }}」のルール (ID: {{ deletingCondition.id }}) を削除します。
                    </span>
                    <span v-else>
                        ルール (ID: {{ deletingCondition?.id }}) を削除します。
                    </span>
                    <br />
                    このルールに紐づく保留中の予約もキャンセルされます。
                </v-card-text>
                <v-card-actions>
                    <v-spacer />
                    <v-btn variant="text" :disabled="isDeleting" @click="isDeleteDialogOpen = false">
                        キャンセル
                    </v-btn>
                    <v-btn variant="flat" color="error" :loading="isDeleting" @click="executeDelete">
                        削除する
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

    </div>
</template>

<script lang="ts" setup>

import { ref, onMounted, onUnmounted } from 'vue';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import ReservationConditionEditDialog from '@/components/Reservations/ReservationConditionEditDialog.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import Message from '@/message';
import ReservationConditions, { type IReservationCondition } from '@/services/ReservationConditions';

// ルール一覧
const conditions = ref<IReservationCondition[]>([]);
const isLoading = ref(true);

// 自動更新用の interval ID を保持
const autoRefreshInterval = ref<number | null>(null);
const AUTO_REFRESH_INTERVAL = 30 * 1000;  // 30秒

// 追加/編集ダイアログ
const isEditDialogOpen = ref(false);
const editingCondition = ref<IReservationCondition | null>(null);

// 削除確認ダイアログ
const isDeleteDialogOpen = ref(false);
const deletingCondition = ref<IReservationCondition | null>(null);
const isDeleting = ref(false);

// ルール一覧を取得する
async function fetchConditions() {
    const result = await ReservationConditions.fetchReservationConditions();
    if (result) {
        conditions.value = result.reservation_conditions;
    }
    isLoading.value = false;
}

// 追加ダイアログを開く
function openAddDialog() {
    editingCondition.value = null;
    isEditDialogOpen.value = true;
}

// 編集ダイアログを開く
function openEditDialog(condition: IReservationCondition) {
    editingCondition.value = condition;
    isEditDialogOpen.value = true;
}

// 削除確認ダイアログを開く
function confirmDelete(condition: IReservationCondition) {
    deletingCondition.value = condition;
    isDeleteDialogOpen.value = true;
}

// 削除を実行する
async function executeDelete() {
    if (!deletingCondition.value) return;
    isDeleting.value = true;
    try {
        const success = await ReservationConditions.deleteReservationCondition(deletingCondition.value.id);
        if (success) {
            Message.success('自動予約ルールを削除しました。');
            isDeleteDialogOpen.value = false;
            deletingCondition.value = null;
            await fetchConditions();
        }
    } finally {
        isDeleting.value = false;
    }
}

// 保存後の処理 (追加/更新ダイアログから呼ばれる)
async function onSaved() {
    await fetchConditions();
}

// 自動更新を開始する
function startAutoRefresh() {
    if (autoRefreshInterval.value === null) {
        fetchConditions();
        autoRefreshInterval.value = window.setInterval(fetchConditions, AUTO_REFRESH_INTERVAL);
    }
}

// 自動更新を停止する
function stopAutoRefresh() {
    if (autoRefreshInterval.value !== null) {
        clearInterval(autoRefreshInterval.value);
        autoRefreshInterval.value = null;
    }
}

onMounted(() => { startAutoRefresh(); });
onUnmounted(() => { stopAutoRefresh(); });

</script>

<style lang="scss" scoped>

.conditions-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
    min-width: 0;
}

.conditions-container {
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
        padding: 16px !important;
    }
    @include smartphone-vertical {
        padding: 8px 8px 20px !important;
    }

    &__header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
    }

    &__title {
        font-size: 1.15rem;
        font-weight: bold;
    }

    &__loading {
        display: flex;
        justify-content: center;
        padding: 60px 0;
    }

    &__empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 60px 20px;
        text-align: center;
    }

    &__empty-icon {
        color: rgb(var(--v-theme-text-darken-1));
        opacity: 0.4;
        margin-bottom: 16px;
    }

    &__empty-message {
        font-size: 1.05rem;
        font-weight: bold;
        color: rgb(var(--v-theme-text));
        margin-bottom: 8px;
    }

    &__empty-sub {
        font-size: 0.875rem;
        color: rgb(var(--v-theme-text-darken-1));
        max-width: 400px;
    }

    &__list {
        width: 100%;
    }
}

.condition-card {
    background: rgb(var(--v-theme-background-lighten-2)) !important;

    &__content {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        padding: 16px !important;
    }

    &__main {
        flex: 1;
        min-width: 0;
    }

    &__header-row {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 8px;
    }

    &__badge {
        font-weight: bold;
    }

    &__id {
        font-size: 0.8rem;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__keyword {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 1rem;
        font-weight: bold;
        margin-bottom: 4px;

        &--empty {
            font-weight: normal;
            font-style: italic;
            color: rgb(var(--v-theme-text-darken-1));
        }
    }

    &__keyword-icon {
        flex-shrink: 0;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__note {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 0.85rem;
        color: rgb(var(--v-theme-text-darken-1));
        margin-bottom: 6px;
    }

    &__note-icon {
        flex-shrink: 0;
    }

    &__tags {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-top: 4px;
    }

    &__actions {
        display: flex;
        flex-direction: column;
        gap: 2px;
        flex-shrink: 0;
    }
}

</style>
