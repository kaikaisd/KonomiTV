
<template>
    <v-dialog v-model="isOpen" max-width="720px" scrollable persistent>
        <v-card class="condition-edit-dialog">
            <v-card-title class="condition-edit-dialog__title">
                {{ isEditMode ? 'キーワード自動予約ルールを編集' : 'キーワード自動予約ルールを追加' }}
            </v-card-title>
            <v-divider />
            <v-card-text class="condition-edit-dialog__content">

                <!-- ルールの有効/無効 -->
                <v-switch v-model="form.is_enabled" label="このルールを有効にする"
                    color="primary" hide-details class="mb-3" />

                <!-- 検索キーワード -->
                <v-text-field v-model="form.keyword" label="検索キーワード"
                    variant="outlined" density="compact" class="mb-3"
                    hint="番組名や説明文に含まれるキーワードを指定します。空白の場合はすべての番組が対象になります。"
                    persistent-hint />

                <!-- 除外キーワード -->
                <v-text-field v-model="form.exclude_keyword" label="除外キーワード"
                    variant="outlined" density="compact" class="mb-3"
                    hint="このキーワードが含まれる番組を対象から除外します。"
                    persistent-hint />

                <!-- メモ -->
                <v-text-field v-model="form.note" label="メモ"
                    variant="outlined" density="compact" class="mb-4"
                    hint="ルールの説明や管理用メモを入力します。"
                    persistent-hint />

                <!-- 検索オプション -->
                <div class="condition-edit-dialog__option-row mb-4">
                    <v-switch v-model="form.is_title_only" label="番組名のみ検索"
                        color="primary" hide-details density="compact" class="condition-edit-dialog__option-switch" />
                    <v-switch v-model="form.is_case_sensitive" label="大文字・小文字を区別"
                        color="primary" hide-details density="compact" class="condition-edit-dialog__option-switch" />
                    <v-switch v-model="form.is_regex_search_enabled" label="正規表現で検索"
                        color="primary" hide-details density="compact" class="condition-edit-dialog__option-switch" />
                </div>

                <v-divider class="mb-4" />

                <!-- チャンネル選択 -->
                <div class="condition-edit-dialog__section-title mb-1">対象チャンネル</div>
                <div class="condition-edit-dialog__section-hint mb-2">
                    選択なしの場合はすべてのチャンネルが対象になります。
                </div>
                <div v-if="isChannelsLoading" class="mb-3">
                    <v-progress-circular indeterminate color="primary" size="20" />
                </div>
                <div v-else class="mb-3">
                    <v-chip v-for="type in availableChannelTypes" :key="type"
                        :color="selectedChannelTypes.includes(type) ? 'primary' : 'default'"
                        :variant="selectedChannelTypes.includes(type) ? 'flat' : 'outlined'"
                        class="mr-1 mb-1" @click="toggleChannelType(type)" style="cursor: pointer;">
                        {{ channelTypeLabel(type) }}
                        <span class="condition-edit-dialog__chip-count">{{ channelsList[type].length }}</span>
                    </v-chip>
                </div>

                <v-divider class="mb-4" />

                <!-- ジャンル選択 -->
                <div class="condition-edit-dialog__section-title mb-1">ジャンル</div>
                <div class="condition-edit-dialog__section-hint mb-2">
                    選択なしの場合はすべてのジャンルが対象になります。
                </div>
                <div class="mb-2">
                    <v-chip v-for="genre in majorGenres" :key="genre"
                        :color="selectedGenres.includes(genre) ? 'primary' : 'default'"
                        :variant="selectedGenres.includes(genre) ? 'flat' : 'outlined'"
                        size="small" class="mr-1 mb-1" @click="toggleGenre(genre)" style="cursor: pointer;">
                        {{ genre }}
                    </v-chip>
                </div>
                <v-switch v-model="genreExcludeMode" label="選択したジャンルを除外する"
                    color="primary" hide-details density="compact" class="mb-4" />

                <v-divider class="mb-4" />

                <!-- 曜日・時間帯 -->
                <div class="condition-edit-dialog__section-title mb-1">曜日・時間帯</div>
                <div class="condition-edit-dialog__section-hint mb-2">
                    選択なしの場合はすべての曜日・時間帯が対象になります。
                </div>
                <div class="mb-2">
                    <v-chip v-for="(day, idx) in weekdayLabels" :key="idx"
                        :color="selectedWeekdays.includes(idx) ? 'primary' : 'default'"
                        :variant="selectedWeekdays.includes(idx) ? 'flat' : 'outlined'"
                        size="small" class="mr-1 mb-1" @click="toggleWeekday(idx)" style="cursor: pointer;">
                        {{ day }}
                    </v-chip>
                </div>
                <v-row v-if="selectedWeekdays.length > 0" class="mb-1">
                    <v-col cols="6">
                        <v-text-field v-model="weekdayTimeStart" label="開始時刻"
                            variant="outlined" density="compact" type="time" clearable
                            hint="未入力の場合は 00:00 (0時)" persistent-hint />
                    </v-col>
                    <v-col cols="6">
                        <v-text-field v-model="weekdayTimeEnd" label="終了時刻"
                            variant="outlined" density="compact" type="time" clearable
                            hint="未入力の場合は 24:00 (深夜0時)" persistent-hint />
                    </v-col>
                </v-row>
                <v-switch v-model="form.is_exclude_date_ranges" label="指定した曜日・時間帯を除外する"
                    color="primary" hide-details density="compact" class="mb-4" />

                <v-divider class="mb-4" />

                <!-- 放送種別フィルタ -->
                <v-select v-model="form.broadcast_type" :items="broadcastTypeItems" item-title="label" item-value="value"
                    label="放送種別" variant="outlined" density="compact" class="mb-3" />

                <!-- 番組長フィルタ -->
                <v-row class="mb-1">
                    <v-col cols="6">
                        <v-text-field v-model="durationMinText" label="最短番組長 (分)"
                            variant="outlined" density="compact" type="number" min="0" clearable
                            hint="未入力の場合は下限なし" persistent-hint />
                    </v-col>
                    <v-col cols="6">
                        <v-text-field v-model="durationMaxText" label="最長番組長 (分)"
                            variant="outlined" density="compact" type="number" min="0" clearable
                            hint="未入力の場合は上限なし" persistent-hint />
                    </v-col>
                </v-row>

                <!-- 重複タイトルチェック -->
                <v-select v-model="form.duplicate_title_check_scope" :items="duplicateCheckItems"
                    item-title="label" item-value="value"
                    label="同タイトル重複チェック" variant="outlined" density="compact" class="mb-3" />
                <v-text-field v-if="form.duplicate_title_check_scope !== 'None'"
                    v-model.number="form.duplicate_title_check_period_days"
                    label="重複チェック対象期間 (日)" variant="outlined" density="compact"
                    type="number" min="1" class="mb-3" />

                <v-divider class="mb-4" />

                <!-- 録画設定 -->
                <div class="condition-edit-dialog__section-title mb-2">録画設定</div>

                <!-- 優先度 -->
                <div class="condition-edit-dialog__priority-label">優先度: {{ recordSettings.priority }}</div>
                <v-slider v-model="recordSettings.priority" :min="1" :max="5" :step="1"
                    color="primary" thumb-label="always" class="condition-edit-dialog__priority-slider mb-4" />

                <!-- 録画マージン -->
                <v-row>
                    <v-col cols="6">
                        <v-text-field v-model="startMarginText" label="録画開始マージン (秒)"
                            variant="outlined" density="compact" type="number" min="0" clearable
                            hint="未入力の場合はデフォルト設定を使用" persistent-hint />
                    </v-col>
                    <v-col cols="6">
                        <v-text-field v-model="endMarginText" label="録画終了マージン (秒)"
                            variant="outlined" density="compact" type="number" min="0" clearable
                            hint="未入力の場合はデフォルト設定を使用" persistent-hint />
                    </v-col>
                </v-row>

                <v-divider class="mb-4" />

                <!-- プレビュー検索 -->
                <div class="condition-edit-dialog__section-title mb-2">プレビュー</div>
                <div class="mb-3">
                    <v-btn :loading="isSearching" variant="tonal" color="primary" size="small"
                        prepend-icon="fluent:search-20-regular" @click="previewSearch">
                        条件に一致する番組を検索
                    </v-btn>
                </div>
                <div v-if="searchResult !== null" class="condition-edit-dialog__preview">
                    <v-chip :color="searchResult.total > 0 ? 'primary' : 'default'"
                        variant="tonal" size="small" class="mb-2">
                        {{ searchResult.total }} 件ヒット
                    </v-chip>
                    <div v-if="searchResult.total === 0" class="condition-edit-dialog__preview-empty">
                        条件に一致する番組はありません。
                    </div>
                    <div v-for="program in searchResult.programs.slice(0, 5)" :key="program.id"
                        class="condition-edit-dialog__preview-item">
                        <span class="condition-edit-dialog__preview-time">
                            {{ dayjs(program.start_time).format('M/D(ddd) HH:mm') }}
                        </span>
                        {{ program.title }}
                    </div>
                    <div v-if="searchResult.total > 5" class="condition-edit-dialog__preview-more">
                        …他 {{ searchResult.total - 5 }} 件
                    </div>
                </div>

            </v-card-text>
            <v-divider />
            <v-card-actions class="condition-edit-dialog__actions">
                <v-spacer />
                <v-btn variant="text" :disabled="isSaving" @click="cancel">キャンセル</v-btn>
                <v-btn variant="flat" color="primary" :loading="isSaving" @click="save">保存</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script lang="ts" setup>

import { ref, computed, watch, nextTick } from 'vue';

import Message from '@/message';
import Channels, { type ChannelType, type ILiveChannelsList } from '@/services/Channels';
import Programs, { type IProgramSearchCondition, type IProgramSearchConditionService,
    type IProgramSearchConditionDate, type IPrograms } from '@/services/Programs';
import ReservationConditions, { type IReservationCondition } from '@/services/ReservationConditions';
import { type IRecordSettings, IRecordSettingsDefault } from '@/services/Reservations';
import { dayjs } from '@/utils';
import { ProgramUtils } from '@/utils/ProgramUtils';


const props = defineProps<{
    modelValue: boolean;
    condition: IReservationCondition | null;
}>();

const emit = defineEmits<{
    'update:modelValue': [value: boolean];
    saved: [];
}>();

const isOpen = computed({
    get: () => props.modelValue,
    set: (value) => emit('update:modelValue', value),
});

const isEditMode = computed(() => props.condition !== null);
const isSaving = ref(false);

// デフォルトの番組検索条件
const defaultSearchCondition = (): IProgramSearchCondition => ({
    is_enabled: true,
    keyword: '',
    exclude_keyword: '',
    note: '',
    is_title_only: false,
    is_case_sensitive: false,
    is_fuzzy_search_enabled: false,
    is_regex_search_enabled: false,
    service_ranges: null,
    genre_ranges: null,
    is_exclude_genre_ranges: false,
    date_ranges: null,
    is_exclude_date_ranges: false,
    duration_range_min: null,
    duration_range_max: null,
    broadcast_type: 'All',
    duplicate_title_check_scope: 'None',
    duplicate_title_check_period_days: 6,
});

// フォームの状態 (番組検索条件)
const form = ref<IProgramSearchCondition>(defaultSearchCondition());

// フォームの状態 (録画設定)
const recordSettings = ref<IRecordSettings>(structuredClone(IRecordSettingsDefault));

// 番組長・マージンの文字列バインディング (null ↔ '' 変換用)
const durationMinText = computed({
    get: () => form.value.duration_range_min !== null ? String(form.value.duration_range_min) : '',
    set: (v) => { form.value.duration_range_min = v !== '' && v !== null ? Number(v) : null; },
});
const durationMaxText = computed({
    get: () => form.value.duration_range_max !== null ? String(form.value.duration_range_max) : '',
    set: (v) => { form.value.duration_range_max = v !== '' && v !== null ? Number(v) : null; },
});
const startMarginText = computed({
    get: () => recordSettings.value.recording_start_margin !== null ? String(recordSettings.value.recording_start_margin) : '',
    set: (v) => { recordSettings.value.recording_start_margin = v !== '' && v !== null ? Number(v) : null; },
});
const endMarginText = computed({
    get: () => recordSettings.value.recording_end_margin !== null ? String(recordSettings.value.recording_end_margin) : '',
    set: (v) => { recordSettings.value.recording_end_margin = v !== '' && v !== null ? Number(v) : null; },
});

// ============================================================
// チャンネル選択
// ============================================================

// チャンネルタイプの日本語ラベル
const CHANNEL_TYPE_LABELS: Record<ChannelType, string> = {
    GR: '地デジ', BS: 'BS', CS: 'CS', CATV: 'CATV', SKY: 'SKY', BS4K: 'BS4K',
};

// ローカルにキャッシュしたチャンネルリスト
const channelsList = ref<ILiveChannelsList>({ GR: [], BS: [], CS: [], CATV: [], SKY: [], BS4K: [] });
const isChannelsLoading = ref(false);

// チャンネルが存在するタイプの一覧
const availableChannelTypes = computed((): ChannelType[] => {
    return (['GR', 'BS', 'CS', 'CATV', 'SKY', 'BS4K'] as ChannelType[])
        .filter(t => channelsList.value[t].length > 0);
});

function channelTypeLabel(type: ChannelType): string {
    return CHANNEL_TYPE_LABELS[type];
}

// 選択中のチャンネルタイプ (UI 専用状態; service_ranges には save/preview 時のみ変換)
const selectedChannelTypes = ref<ChannelType[]>([]);

function toggleChannelType(type: ChannelType): void {
    const idx = selectedChannelTypes.value.indexOf(type);
    if (idx >= 0) {
        selectedChannelTypes.value.splice(idx, 1);
    } else {
        selectedChannelTypes.value.push(type);
    }
}

// ============================================================
// ジャンル選択
// ============================================================

// ARIB-STD-B10 の主要ジャンルリスト (「拡張」「その他」は除外)
const majorGenres: string[] = (Object.values(ProgramUtils.CONTENT_TYPE) as [string, Record<number, string>][])
    .map(([name]) => name)
    .filter(name => !['拡張', 'その他'].includes(name));

// 選択中のジャンル (UI 専用状態)
const selectedGenres = ref<string[]>([]);

// true のとき選択ジャンルを「除外」、false のとき「含む」
const genreExcludeMode = ref(false);

function toggleGenre(genre: string): void {
    const idx = selectedGenres.value.indexOf(genre);
    if (idx >= 0) {
        selectedGenres.value.splice(idx, 1);
    } else {
        selectedGenres.value.push(genre);
    }
}

// ============================================================
// 曜日・時間帯
// ============================================================

// 0=日, 1=月, ..., 6=土 (EDCB/Mirakurun 規約に合わせた曜日番号)
const weekdayLabels = ['日', '月', '火', '水', '木', '金', '土'];

// 選択中の曜日 (UI 専用状態)
const selectedWeekdays = ref<number[]>([]);

// 曜日ごとの時間帯 (HH:MM 形式, 空文字は未指定)
const weekdayTimeStart = ref<string>('');
const weekdayTimeEnd = ref<string>('');

function toggleWeekday(day: number): void {
    const idx = selectedWeekdays.value.indexOf(day);
    if (idx >= 0) {
        selectedWeekdays.value.splice(idx, 1);
    } else {
        selectedWeekdays.value.push(day);
    }
}

// "HH:MM" 文字列を [hour, minute] に変換するヘルパー
function parseTime(time: string): [number, number] {
    if (!time || !time.includes(':')) return [0, 0];
    const parts = time.split(':');
    return [Number(parts[0]) || 0, Number(parts[1]) || 0];
}

// ============================================================
// プレビュー検索
// ============================================================

const isSearching = ref(false);
const searchResult = ref<IPrograms | null>(null);

async function previewSearch(): Promise<void> {
    isSearching.value = true;
    searchResult.value = null;
    try {
        searchResult.value = await Programs.searchPrograms(buildSearchCondition());
    } finally {
        isSearching.value = false;
    }
}

// ============================================================
// フォーム → API リクエスト変換
// ============================================================

/**
 * UI 専用状態 (selectedChannelTypes / selectedGenres / selectedWeekdays など) を
 * form.value の各フィールドに統合した完全な IProgramSearchCondition を返す。
 * 保存・プレビュー時のみ呼ばれる。
 */
function buildSearchCondition(): IProgramSearchCondition {
    const condition: IProgramSearchCondition = { ...form.value };

    // チャンネルタイプ → service_ranges (選択タイプに属する全チャンネルの service 情報を列挙)
    if (selectedChannelTypes.value.length === 0) {
        condition.service_ranges = null;
    } else {
        const ranges: IProgramSearchConditionService[] = [];
        for (const type of selectedChannelTypes.value) {
            for (const ch of channelsList.value[type]) {
                if (!ch.is_radiochannel) {
                    ranges.push({
                        network_id: ch.network_id,
                        transport_stream_id: ch.transport_stream_id ?? 0,
                        service_id: ch.service_id,
                    });
                }
            }
        }
        condition.service_ranges = ranges.length > 0 ? ranges : null;
    }

    // ジャンル → genre_ranges + is_exclude_genre_ranges
    if (selectedGenres.value.length === 0) {
        condition.genre_ranges = null;
        condition.is_exclude_genre_ranges = false;
    } else {
        // middle を空文字にすることで大分類のみマッチ (EDCB/Mirakurun 側で "空 = 全中分類" として扱われる)
        condition.genre_ranges = selectedGenres.value.map(name => ({ major: name, middle: '' }));
        condition.is_exclude_genre_ranges = genreExcludeMode.value;
    }

    // 曜日・時間帯 → date_ranges (各曜日を独立したレンジとして列挙)
    if (selectedWeekdays.value.length === 0) {
        condition.date_ranges = null;
    } else {
        const [startH, startM] = parseTime(weekdayTimeStart.value);
        const [endH, endM] = parseTime(weekdayTimeEnd.value);
        condition.date_ranges = [...selectedWeekdays.value].sort((a, b) => a - b).map((day): IProgramSearchConditionDate => ({
            start_day_of_week: day,
            start_hour: startH,
            start_minute: startM,
            end_day_of_week: day,
            end_hour: endH,
            end_minute: endM,
        }));
    }

    return condition;
}

// ============================================================
// UI 状態をフォームから復元 (編集モードで開いたとき)
// ============================================================

function deriveUiStateFromForm(): void {
    // チャンネルタイプを service_ranges から逆引き
    if (!form.value.service_ranges || form.value.service_ranges.length === 0) {
        selectedChannelTypes.value = [];
    } else {
        const types: ChannelType[] = [];
        for (const type of (['GR', 'BS', 'CS', 'CATV', 'SKY', 'BS4K'] as ChannelType[])) {
            if (channelsList.value[type].some(ch =>
                form.value.service_ranges!.some(s =>
                    s.network_id === ch.network_id && s.service_id === ch.service_id,
                ),
            )) {
                types.push(type);
            }
        }
        selectedChannelTypes.value = types;
    }

    // ジャンルを genre_ranges から復元
    if (!form.value.genre_ranges || form.value.genre_ranges.length === 0) {
        selectedGenres.value = [];
        genreExcludeMode.value = false;
    } else {
        selectedGenres.value = form.value.genre_ranges.map(g => g.major).filter(m => !!m);
        genreExcludeMode.value = form.value.is_exclude_genre_ranges;
    }

    // 曜日・時間帯を date_ranges から復元
    if (!form.value.date_ranges || form.value.date_ranges.length === 0) {
        selectedWeekdays.value = [];
        weekdayTimeStart.value = '';
        weekdayTimeEnd.value = '';
    } else {
        // 一意の曜日を昇順に並べる
        selectedWeekdays.value = [...new Set(form.value.date_ranges.map(d => d.start_day_of_week))].sort((a, b) => a - b);
        // 最初のエントリの時刻を代表として復元 (全日同一時刻という前提)
        const first = form.value.date_ranges[0];
        if (first.start_hour === 0 && first.start_minute === 0 && first.end_hour === 0 && first.end_minute === 0) {
            weekdayTimeStart.value = '';
            weekdayTimeEnd.value = '';
        } else {
            weekdayTimeStart.value = `${String(first.start_hour).padStart(2, '0')}:${String(first.start_minute).padStart(2, '0')}`;
            weekdayTimeEnd.value = `${String(first.end_hour).padStart(2, '0')}:${String(first.end_minute).padStart(2, '0')}`;
        }
    }

    // プレビュー結果をリセット
    searchResult.value = null;
}

// ============================================================
// ダイアログの開閉制御
// ============================================================

// ダイアログが開いたらチャンネルリストを取得し、フォームを初期化する
// Bug fix: await nextTick() で condition プロップの更新が確実に反映されてからフォームを読み取る
watch(() => props.modelValue, async (opened) => {
    if (!opened) return;

    // チャンネルリストの取得 (未取得の場合のみ API を叩く)
    if (availableChannelTypes.value.length === 0) {
        isChannelsLoading.value = true;
        try {
            const result = await Channels.fetchAllChannels();
            if (result) channelsList.value = result;
        } finally {
            isChannelsLoading.value = false;
        }
    }

    // modelValue と condition は同一 tick に設定されるため、
    // nextTick で DOM 更新サイクルを経てから props.condition を確実に読み取る
    await nextTick();

    if (props.condition) {
        // 編集モード: 既存のルールデータをディープコピーしてフォームに設定する
        // JSON.parse/stringify により Vue のリアクティブプロキシを解除してからコピーする
        form.value = JSON.parse(JSON.stringify(props.condition.program_search_condition));
        recordSettings.value = JSON.parse(JSON.stringify(props.condition.record_settings));
    } else {
        // 追加モード: デフォルト値でフォームをリセットする
        form.value = defaultSearchCondition();
        recordSettings.value = JSON.parse(JSON.stringify(IRecordSettingsDefault));
    }

    // UI 専用状態をフォームから復元
    deriveUiStateFromForm();
});

// 放送種別の選択肢
const broadcastTypeItems = [
    { label: 'すべて', value: 'All' },
    { label: '無料放送のみ', value: 'FreeOnly' },
    { label: '有料放送のみ', value: 'PaidOnly' },
];

// 重複チェックの選択肢
const duplicateCheckItems = [
    { label: 'チェックしない', value: 'None' },
    { label: '同じチャンネルのみ', value: 'SameChannelOnly' },
    { label: 'すべてのチャンネル', value: 'AllChannels' },
];

// ダイアログを閉じる
function cancel() {
    isOpen.value = false;
}

// ルールを保存する
async function save() {
    isSaving.value = true;
    try {
        const searchCondition = buildSearchCondition();
        let success: boolean | IReservationCondition | null;
        if (isEditMode.value && props.condition) {
            // 更新
            success = await ReservationConditions.updateReservationCondition(
                props.condition.id,
                searchCondition,
                recordSettings.value,
            );
        } else {
            // 新規追加
            success = await ReservationConditions.addReservationCondition(
                searchCondition,
                recordSettings.value,
            );
        }
        if (success !== null && success !== false) {
            Message.success(isEditMode.value ? '自動予約ルールを更新しました。' : '自動予約ルールを追加しました。');
            isOpen.value = false;
            emit('saved');
        }
    } finally {
        isSaving.value = false;
    }
}

</script>

<style lang="scss" scoped>

.condition-edit-dialog {
    &__title {
        font-size: 1.1rem;
        font-weight: bold;
        padding: 16px 20px;
    }

    &__content {
        padding: 20px;
    }

    &__option-row {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 16px;
    }

    &__option-switch {
        flex: 0 0 auto;
    }

    &__section-title {
        font-size: 0.875rem;
        font-weight: 600;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__section-hint {
        font-size: 0.8rem;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__chip-count {
        font-size: 0.75rem;
        opacity: 0.7;
        margin-left: 4px;
    }

    &__priority-label {
        font-size: 0.85rem;
        color: rgb(var(--v-theme-text-darken-1));
        margin-bottom: 4px;
    }

    &__priority-slider {
        padding: 0 4px;
    }

    &__actions {
        padding: 12px 16px;
    }

    &__preview {
        background: rgb(var(--v-theme-background-lighten-1));
        border-radius: 6px;
        padding: 12px 14px;
        margin-top: 4px;
    }

    &__preview-empty {
        font-size: 0.85rem;
        color: rgb(var(--v-theme-text-darken-1));
    }

    &__preview-item {
        font-size: 0.85rem;
        padding: 3px 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    &__preview-time {
        font-size: 0.8rem;
        color: rgb(var(--v-theme-text-darken-1));
        margin-right: 6px;
    }

    &__preview-more {
        font-size: 0.8rem;
        color: rgb(var(--v-theme-text-darken-1));
        margin-top: 4px;
    }
}

</style>
