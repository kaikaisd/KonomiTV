
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
                    選択なしの場合はすべてのチャンネルが対象になります。グループをクリックすると一括選択、行をクリックすると個別選択できます。
                </div>
                <div v-if="isChannelsLoading" class="mb-3">
                    <v-progress-circular indeterminate color="primary" size="20" />
                </div>
                <div v-else class="mb-3">
                    <!-- タイプ別一括選択ボタン -->
                    <div class="condition-edit-dialog__type-row mb-2">
                        <button v-for="type in availableChannelTypes" :key="type"
                            class="condition-edit-dialog__type-btn"
                            :class="{
                                'condition-edit-dialog__type-btn--full': isTypeFullySelected(type),
                                'condition-edit-dialog__type-btn--partial': isTypePartiallySelected(type) && !isTypeFullySelected(type),
                            }"
                            @click="toggleChannelType(type)">
                            {{ channelTypeLabel(type) }}
                        </button>
                    </div>
                    <!-- 個別チャンネル選択リスト -->
                    <div class="condition-edit-dialog__channel-listbox">
                        <template v-for="type in availableChannelTypes" :key="type">
                            <!-- タイプ区切りヘッダー -->
                            <div class="condition-edit-dialog__channel-type-header">
                                {{ channelTypeLabel(type) }}
                            </div>
                            <div v-for="ch in channelsList[type].filter((c: ILiveChannel) => !c.is_radiochannel)" :key="channelKey(ch)"
                                class="condition-edit-dialog__channel-option"
                                :class="{ 'condition-edit-dialog__channel-option--selected': isChannelSelected(ch) }"
                                @click="toggleChannel(ch)">
                                <img class="condition-edit-dialog__channel-icon" loading="lazy" decoding="async"
                                    :src="`${Utils.api_base_url}/channels/${ch.id}/logo`">
                                <span class="condition-edit-dialog__channel-option-name">{{ ch.name }}</span>
                                <svg v-if="isChannelSelected(ch)" class="condition-edit-dialog__channel-option-check"
                                    viewBox="0 0 24 24" width="16" height="16">
                                    <path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                                </svg>
                            </div>
                        </template>
                    </div>
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
                        <img class="condition-edit-dialog__preview-channel-logo" loading="lazy" decoding="async"
                            :src="`${Utils.api_base_url}/channels/${program.channel_id}/logo`">
                        <span class="condition-edit-dialog__preview-channel-name">{{ getChannelName(program) }}</span>
                        <span class="condition-edit-dialog__preview-title">{{ program.title }}</span>
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
import Channels, { type ChannelType, type ILiveChannel, type ILiveChannelsList } from '@/services/Channels';
import Programs, { type IProgram, type IProgramSearchCondition, type IProgramSearchConditionService,
    type IProgramSearchConditionDate, type IPrograms } from '@/services/Programs';
import ReservationConditions, { type IReservationCondition } from '@/services/ReservationConditions';
import { type IRecordSettings, IRecordSettingsDefault } from '@/services/Reservations';
import Utils, { dayjs } from '@/utils';
import { ProgramUtils } from '@/utils/ProgramUtils';


const props = defineProps<{
    modelValue: boolean;
    condition: IReservationCondition | null;
    // 新規追加モード時にキーワード欄に初期値を設定する (番組詳細ドロワーからの呼び出し用)
    initialKeyword?: string;
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
    // ラジオチャンネル以外の選択可能なチャンネルが1件以上あるタイプのみに絞る
    return (['GR', 'BS', 'CS', 'CATV', 'SKY', 'BS4K'] as ChannelType[])
        .filter(t => channelsList.value[t].some((c: ILiveChannel) => !c.is_radiochannel));
});

function channelTypeLabel(type: ChannelType): string {
    return CHANNEL_TYPE_LABELS[type];
}

// 個別チャンネルの一意キー: "{network_id}_{service_id}"
function channelKey(ch: { network_id: number; service_id: number }): string {
    return `${ch.network_id}_${ch.service_id}`;
}

// 選択中のチャンネルを個別 ID (network_id_service_id) のセットで管理する (UI 専用状態)
// タイプ単位の一括選択も個別選択も、全てここに集約して service_ranges に変換する
const selectedChannelIds = ref<string[]>([]);


// 指定チャンネルが選択中かどうか
function isChannelSelected(ch: { network_id: number; service_id: number }): boolean {
    return selectedChannelIds.value.includes(channelKey(ch));
}

// タイプ内の全非ラジオチャンネルが全て選択中かどうか
function isTypeFullySelected(type: ChannelType): boolean {
    const chs = channelsList.value[type].filter(c => !c.is_radiochannel);
    return chs.length > 0 && chs.every(ch => isChannelSelected(ch));
}

// タイプ内に1つ以上選択中のチャンネルがあるかどうか (部分選択・全選択 両方 true)
function isTypePartiallySelected(type: ChannelType): boolean {
    return channelsList.value[type].some(ch => !ch.is_radiochannel && isChannelSelected(ch));
}

// タイプチップをクリック: 全選択 ↔ 全解除 のトグル
function toggleChannelType(type: ChannelType): void {
    const chs = channelsList.value[type].filter(c => !c.is_radiochannel);
    if (isTypeFullySelected(type)) {
        // 全選択 → 全解除
        const removeKeys = new Set(chs.map(channelKey));
        selectedChannelIds.value = selectedChannelIds.value.filter(id => !removeKeys.has(id));
    } else {
        // 部分選択 or 未選択 → 全選択 (重複なし)
        const existing = new Set(selectedChannelIds.value);
        for (const ch of chs) {
            existing.add(channelKey(ch));
        }
        selectedChannelIds.value = [...existing];
    }
}

// 個別チャンネルチップをクリック: 選択 ↔ 解除 のトグル
function toggleChannel(ch: { network_id: number; service_id: number }): void {
    const key = channelKey(ch);
    const idx = selectedChannelIds.value.indexOf(key);
    if (idx >= 0) {
        selectedChannelIds.value.splice(idx, 1);
    } else {
        selectedChannelIds.value.push(key);
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

// 番組情報からチャンネル名を取得する (channelsList を network_id + service_id でマッチ)
function getChannelName(program: IProgram): string {
    for (const type of (['GR', 'BS', 'CS', 'CATV', 'SKY', 'BS4K'] as ChannelType[])) {
        const ch = channelsList.value[type].find((c: ILiveChannel) => c.network_id === program.network_id && c.service_id === program.service_id);
        if (ch) return ch.name;
    }
    return '';
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

    // 選択中の個別チャンネル ID → service_ranges
    if (selectedChannelIds.value.length === 0) {
        condition.service_ranges = null;
    } else {
        const selectedSet = new Set(selectedChannelIds.value);
        const ranges: IProgramSearchConditionService[] = [];
        for (const type of availableChannelTypes.value) {
            for (const ch of channelsList.value[type]) {
                if (!ch.is_radiochannel && selectedSet.has(channelKey(ch))) {
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
    // service_ranges から個別チャンネル ID を復元
    if (!form.value.service_ranges || form.value.service_ranges.length === 0) {
        selectedChannelIds.value = [];
    } else {
        const ids: string[] = [];
        for (const type of (['GR', 'BS', 'CS', 'CATV', 'SKY', 'BS4K'] as ChannelType[])) {
            for (const ch of channelsList.value[type]) {
                if (!ch.is_radiochannel && form.value.service_ranges.some(s =>
                    s.network_id === ch.network_id && s.service_id === ch.service_id,
                )) {
                    ids.push(channelKey(ch));
                }
            }
        }
        selectedChannelIds.value = ids;
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
        // initialKeyword が指定されている場合はキーワード欄に初期値を設定する
        if (props.initialKeyword) {
            form.value.keyword = props.initialKeyword;
            form.value.is_title_only = true;
        }
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
    // キーワードとメモの両方が空の場合は保存を拒否する (ルール名なしでの登録防止)
    if (!form.value.keyword.trim() && !form.value.note.trim()) {
        Message.error('検索キーワードまたはメモを入力してください。');
        return;
    }
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

    &__type-row {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
    }

    &__type-btn {
        flex: 1 1 auto;
        min-width: 52px;
        padding: 6px 12px;
        border-radius: 6px;
        border: 1px solid rgba(var(--v-theme-on-surface), 0.3);
        background: transparent;
        color: rgb(var(--v-theme-on-surface));
        font-size: 0.85rem;
        font-weight: 500;
        cursor: pointer;
        user-select: none;
        transition: background-color 0.15s, border-color 0.15s, color 0.15s;

        &:hover {
            background-color: rgba(var(--v-theme-on-surface), 0.06);
        }

        &--partial {
            border-color: rgb(var(--v-theme-primary));
            color: rgb(var(--v-theme-primary));
            background-color: rgba(var(--v-theme-primary), 0.08);
        }

        &--full {
            border-color: rgb(var(--v-theme-primary));
            background-color: rgb(var(--v-theme-primary));
            color: #fff;
        }
    }

    &__channel-listbox {
        max-height: 240px;
        overflow-y: auto;
        border: 1px solid rgba(var(--v-theme-on-surface), 0.23);
        border-radius: 6px;
    }

    &__channel-type-header {
        font-size: 0.75rem;
        font-weight: 600;
        color: rgb(var(--v-theme-text-darken-1));
        padding: 4px 10px;
        background: rgba(var(--v-theme-on-surface), 0.05);
        border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
    }

    &__channel-option {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 6px 10px;
        min-height: 52px;
        cursor: pointer;
        user-select: none;
        border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
        transition: background-color 0.12s;

        &:last-child {
            border-bottom: none;
        }

        &:hover {
            background-color: rgba(var(--v-theme-on-surface), 0.04);
        }

        &--selected {
            background-color: rgba(var(--v-theme-primary), 0.12);
        }
    }

    &__channel-icon {
        width: 72px;
        height: 40px;
        object-fit: contain;
        flex-shrink: 0;
    }

    &__channel-option-name {
        flex: 1;
        font-size: 1rem;
        line-height: 1.4;
    }

    &__channel-option-check {
        color: rgb(var(--v-theme-primary));
        flex-shrink: 0;
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
        display: flex;
        align-items: center;
        gap: 5px;
        font-size: 0.85rem;
        padding: 3px 0;
        overflow: hidden;
    }

    &__preview-channel-logo {
        width: 24px;
        height: 14px;
        object-fit: contain;
        flex-shrink: 0;
    }

    &__preview-channel-name {
        font-size: 0.78rem;
        color: rgb(var(--v-theme-text-darken-1));
        white-space: nowrap;
        flex-shrink: 0;
        max-width: 80px;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    &__preview-title {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        min-width: 0;
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
