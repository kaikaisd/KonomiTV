<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="encoding-container-wrapper">
                <SPHeaderBar />
                <div class="encoding-container">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: 'エンコード', path: '/encoding/', disabled: true },
                    ]" />

                    <!-- サマリーカード: ステータスごとの件数 -->
                    <div class="encoding-container__summary">
                        <v-card class="encoding-container__summary-card" elevation="1"
                            v-for="summary in statusSummary" :key="summary.label">
                            <v-card-text class="encoding-container__summary-card-content">
                                <div class="encoding-container__summary-card-count" :style="{ color: summary.color }">
                                    {{ summary.count }}
                                </div>
                                <div class="encoding-container__summary-card-label">{{ summary.label }}</div>
                            </v-card-text>
                        </v-card>
                    </div>

                    <!-- 現在エンコード中のタスク -->
                    <div v-if="encodingTask" class="encoding-container__current">
                        <h3 class="encoding-container__section-title">エンコード中</h3>
                        <v-card class="encoding-container__current-card" elevation="2">
                            <v-card-text>
                                <div class="encoding-container__current-header">
                                    <v-chip color="blue" size="small" variant="flat">Encoding</v-chip>
                                    <v-chip size="small" variant="tonal">{{ encodingTask.encoder_type }}</v-chip>
                                    <v-chip size="small" variant="tonal">{{ encodingTask.video_codec }}</v-chip>
                                </div>
                                <div class="encoding-container__current-file">
                                    {{ getFileName(encodingTask.source_file_path) }}
                                </div>
                                <v-progress-linear
                                    class="encoding-container__current-progress"
                                    :model-value="encodingTask.progress"
                                    color="blue"
                                    height="8"
                                    rounded
                                />
                                <div class="encoding-container__current-info">
                                    <span>{{ encodingTask.progress.toFixed(1) }}%</span>
                                    <span v-if="encodingTask.encoding_started_at">
                                        開始: {{ formatTime(encodingTask.encoding_started_at) }}
                                    </span>
                                    <span>ビットレート: {{ encodingTask.video_bitrate }}</span>
                                </div>
                                <div class="encoding-container__current-actions">
                                    <v-btn size="small" color="error" variant="tonal" @click="cancelTask(encodingTask.id)">
                                        キャンセル
                                    </v-btn>
                                </div>
                            </v-card-text>
                        </v-card>
                    </div>

                    <!-- キュー一覧 -->
                    <div class="encoding-container__queue">
                        <h3 class="encoding-container__section-title">エンコードキュー</h3>

                        <!-- フィルターチップ -->
                        <div class="encoding-container__filters">
                            <v-chip v-for="filter in statusFilters" :key="filter.value"
                                :variant="selectedFilter === filter.value ? 'flat' : 'outlined'"
                                :color="selectedFilter === filter.value ? 'primary' : undefined"
                                size="small"
                                @click="selectedFilter = filter.value">
                                {{ filter.label }}
                            </v-chip>
                        </div>

                        <!-- タスクリスト -->
                        <div v-if="filteredTasks.length > 0" class="encoding-container__task-list">
                            <v-card v-for="task in filteredTasks" :key="task.id"
                                class="encoding-container__task-card" elevation="1">
                                <v-card-text class="encoding-container__task-card-content">
                                    <div class="encoding-container__task-card-left">
                                        <v-chip :color="getStatusColor(task.status)" size="x-small" variant="flat">
                                            {{ getStatusLabel(task.status) }}
                                        </v-chip>
                                        <div class="encoding-container__task-card-file">
                                            {{ getFileName(task.source_file_path) }}
                                        </div>
                                        <div class="encoding-container__task-card-meta">
                                            <span>{{ task.encoder_type }} / {{ task.video_codec }}</span>
                                            <span>{{ task.video_bitrate }}</span>
                                            <span v-if="task.priority > 0">優先度: {{ task.priority }}</span>
                                            <span>追加: {{ formatTime(task.added_at) }}</span>
                                        </div>
                                        <!-- 進捗バー (エンコード中のタスクのみ) -->
                                        <v-progress-linear v-if="task.status === 'Encoding'"
                                            :model-value="task.progress" color="blue" height="4" rounded
                                            class="encoding-container__task-card-progress" />
                                        <!-- エラーメッセージ (失敗時のみ) -->
                                        <div v-if="task.status === 'Failed' && task.fail_reason"
                                            class="encoding-container__task-card-error">
                                            {{ task.fail_reason }}
                                        </div>
                                    </div>
                                    <div class="encoding-container__task-card-actions">
                                        <v-btn v-if="task.status === 'Pending' || task.status === 'Encoding'"
                                            icon size="small" variant="text" color="error"
                                            @click="cancelTask(task.id)">
                                            <Icon icon="fluent:dismiss-20-regular" width="18px" />
                                        </v-btn>
                                        <v-btn v-if="task.status === 'Failed' || task.status === 'Cancelled'"
                                            icon size="small" variant="text" color="primary"
                                            @click="retryTask(task.id)">
                                            <Icon icon="fluent:arrow-counterclockwise-20-regular" width="18px" />
                                        </v-btn>
                                        <v-btn v-if="task.status === 'Completed' || task.status === 'Failed' || task.status === 'Cancelled'"
                                            icon size="small" variant="text"
                                            @click="deleteTask(task.id)">
                                            <Icon icon="fluent:delete-20-regular" width="18px" />
                                        </v-btn>
                                    </div>
                                </v-card-text>
                            </v-card>
                        </div>

                        <!-- 空状態 -->
                        <div v-else-if="!isLoading" class="encoding-container__empty">
                            <Icon icon="fluent:video-clip-20-regular" width="48px" class="encoding-container__empty-icon" />
                            <div class="encoding-container__empty-message">
                                {{ selectedFilter === 'all' ? 'エンコードタスクはありません。' : `${getFilterLabel(selectedFilter)}のタスクはありません。` }}
                            </div>
                            <div class="encoding-container__empty-sub">
                                録画番組からエンコードタスクを追加できます。
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    </div>
</template>
<script lang="ts" setup>

import { computed, onMounted, onUnmounted, ref } from 'vue';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import EncodingTasks, { IEncodingTask, IEncodingTaskList, EncodingTaskStatusType } from '@/services/EncodingTasks';
import { dayjs } from '@/utils';

// エンコードタスクの一覧
const allTasks = ref<IEncodingTask[]>([]);
const isLoading = ref(true);

// SSE 接続
let eventSource: EventSource | null = null;

// フィルター
type FilterValue = 'all' | EncodingTaskStatusType;
const selectedFilter = ref<FilterValue>('all');

const statusFilters: { label: string; value: FilterValue }[] = [
    { label: 'すべて', value: 'all' },
    { label: '待機中', value: 'Pending' },
    { label: 'エンコード中', value: 'Encoding' },
    { label: '完了', value: 'Completed' },
    { label: '失敗', value: 'Failed' },
    { label: 'キャンセル', value: 'Cancelled' },
];

// 現在エンコード中のタスク
const encodingTask = computed<IEncodingTask | null>(() => {
    return allTasks.value.find(t => t.status === 'Encoding') ?? null;
});

// フィルター適用後のタスク一覧 (エンコード中のタスクは上部に別表示するため除外)
const filteredTasks = computed<IEncodingTask[]>(() => {
    let tasks = allTasks.value;
    if (selectedFilter.value !== 'all') {
        tasks = tasks.filter(t => t.status === selectedFilter.value);
    }
    return tasks;
});

// ステータスごとの集計
const statusSummary = computed(() => [
    { label: '待機中', count: allTasks.value.filter(t => t.status === 'Pending').length, color: 'rgb(var(--v-theme-text))' },
    { label: 'エンコード中', count: allTasks.value.filter(t => t.status === 'Encoding').length, color: '#2196F3' },
    { label: '完了', count: allTasks.value.filter(t => t.status === 'Completed').length, color: '#4CAF50' },
    { label: '失敗', count: allTasks.value.filter(t => t.status === 'Failed').length, color: '#F44336' },
]);

// ステータスの色を返す
const getStatusColor = (status: EncodingTaskStatusType): string => {
    switch (status) {
        case 'Pending': return 'grey';
        case 'Encoding': return 'blue';
        case 'Completed': return 'success';
        case 'Failed': return 'error';
        case 'Cancelled': return 'warning';
        default: return 'grey';
    }
};

// ステータスの日本語ラベルを返す
const getStatusLabel = (status: EncodingTaskStatusType): string => {
    switch (status) {
        case 'Pending': return '待機中';
        case 'Encoding': return 'エンコード中';
        case 'Completed': return '完了';
        case 'Failed': return '失敗';
        case 'Cancelled': return 'キャンセル';
        default: return status;
    }
};

// フィルターのラベルを返す
const getFilterLabel = (filter: FilterValue): string => {
    return statusFilters.find(f => f.value === filter)?.label ?? filter;
};

// ファイルパスからファイル名を取得する
const getFileName = (filePath: string): string => {
    // Windows と Linux 両方のパス区切り文字に対応
    const parts = filePath.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1] || filePath;
};

// 日時文字列をフォーマットする
const formatTime = (timeStr: string | null): string => {
    if (!timeStr) return '-';
    return dayjs(timeStr).format('MM/DD HH:mm');
};

// タスクをキャンセルする
const cancelTask = async (taskId: number) => {
    await EncodingTasks.update(taskId, { status: 'Cancelled' });
};

// タスクをリトライする
const retryTask = async (taskId: number) => {
    await EncodingTasks.retry(taskId);
};

// タスクを削除する
const deleteTask = async (taskId: number) => {
    await EncodingTasks.delete(taskId);
};

// SSE 接続を開始してリアルタイム更新を受信する
const startSSE = () => {
    const baseUrl = `${location.protocol}//${location.host}`;
    eventSource = new EventSource(`${baseUrl}/api/encoding-tasks/events`);

    // 初回接続時のタスク一覧
    eventSource.addEventListener('initial_update', (event: MessageEvent) => {
        const data: IEncodingTaskList = JSON.parse(event.data);
        allTasks.value = data.encoding_tasks;
        isLoading.value = false;
    });

    // タスク一覧の更新
    eventSource.addEventListener('tasks_update', (event: MessageEvent) => {
        const data: IEncodingTaskList = JSON.parse(event.data);
        allTasks.value = data.encoding_tasks;
    });

    // エラー時に再接続
    eventSource.onerror = () => {
        eventSource?.close();
        // 3秒後に再接続
        setTimeout(startSSE, 3000);
    };
};

// SSE 接続を停止する
const stopSSE = () => {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
};

onMounted(() => {
    startSSE();
});

onUnmounted(() => {
    stopSSE();
});

</script>
<style lang="scss" scoped>

.encoding-container-wrapper {
    display: flex;
    flex-direction: column;
    width: 100%;
    min-width: 0;
}

.encoding-container {
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

    // サマリーカード
    &__summary {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 24px;

        @include smartphone-vertical {
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            margin-bottom: 16px;
        }
    }

    &__summary-card {
        background: rgb(var(--v-theme-background-lighten-2)) !important;

        &-content {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 12px !important;
        }

        &-count {
            font-size: 1.8rem;
            font-weight: bold;
            line-height: 1.2;
        }

        &-label {
            font-size: 0.8rem;
            color: rgb(var(--v-theme-text-darken-1));
            margin-top: 2px;
        }
    }

    // セクションタイトル
    &__section-title {
        font-size: 1.05rem;
        font-weight: bold;
        margin-bottom: 12px;
    }

    // 現在エンコード中のタスク
    &__current {
        margin-bottom: 24px;
    }

    &__current-card {
        background: rgb(var(--v-theme-background-lighten-2)) !important;
    }

    &__current-header {
        display: flex;
        gap: 6px;
        margin-bottom: 8px;
    }

    &__current-file {
        font-size: 0.95rem;
        font-weight: 500;
        margin-bottom: 10px;
        word-break: break-all;
    }

    &__current-progress {
        margin-bottom: 8px;
    }

    &__current-info {
        display: flex;
        gap: 16px;
        font-size: 0.8rem;
        color: rgb(var(--v-theme-text-darken-1));
        margin-bottom: 8px;
        flex-wrap: wrap;
    }

    &__current-actions {
        display: flex;
        justify-content: flex-end;
    }

    // フィルター
    &__filters {
        display: flex;
        gap: 8px;
        margin-bottom: 16px;
        flex-wrap: wrap;
    }

    // タスクリスト
    &__task-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    &__task-card {
        background: rgb(var(--v-theme-background-lighten-2)) !important;

        &-content {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            padding: 12px 14px !important;
        }

        &-left {
            flex: 1;
            min-width: 0;
        }

        &-file {
            font-size: 0.9rem;
            font-weight: 500;
            margin-top: 6px;
            word-break: break-all;
        }

        &-meta {
            display: flex;
            gap: 12px;
            font-size: 0.75rem;
            color: rgb(var(--v-theme-text-darken-1));
            margin-top: 4px;
            flex-wrap: wrap;
        }

        &-progress {
            margin-top: 6px;
        }

        &-error {
            font-size: 0.75rem;
            color: rgb(var(--v-theme-error));
            margin-top: 4px;
            word-break: break-all;
        }

        &-actions {
            display: flex;
            gap: 2px;
            flex-shrink: 0;
        }
    }

    // 空状態
    &__empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 48px 16px;
        text-align: center;

        &-icon {
            color: rgb(var(--v-theme-text-darken-1));
            margin-bottom: 12px;
            opacity: 0.5;
        }

        &-message {
            font-size: 0.95rem;
            font-weight: 500;
            margin-bottom: 4px;
        }

        &-sub {
            font-size: 0.8rem;
            color: rgb(var(--v-theme-text-darken-1));
        }
    }
}

</style>
