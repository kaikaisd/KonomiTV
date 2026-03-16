<template>
    <!-- ベース画面の中にそれぞれの設定画面で異なる部分を記述する -->
    <SettingsBase>
        <h2 class="settings__heading">
            <a v-ripple class="settings__back-button" @click="$router.back()">
                <Icon icon="fluent:chevron-left-12-filled" width="27px" />
            </a>
            <Icon icon="mdi:bell" width="22px" style="margin: 0 3px;" />
            <span class="ml-3">通知</span>
        </h2>
        <div class="settings__content">
            <!-- Telegram 通知セクション -->
            <div class="settings__content-heading">
                <Icon icon="mdi:send" width="22px" style="margin-right: 8px;" />Telegram 通知
            </div>
            <div class="settings__item settings__item--switch">
                <div class="settings__item-heading">録画完了通知を有効にする</div>
                <div class="settings__item-label">
                    録画が完了したときに Telegram Bot 経由でサムネイル・番組情報・再生リンクを通知します。<br>
                    事前に <strong>@BotFather</strong> で Bot を作成し、トークンとチャット ID を取得してください。<br>
                </div>
                <v-switch class="settings__item-switch" color="primary" hide-details
                    v-model="server_settings.notification.telegram_notification_enabled"
                    @update:modelValue="onSettingChanged()" />
            </div>
            <v-divider class="mt-6" />
            <!-- Telegram 詳細設定 (有効時のみ操作可能) -->
            <div :class="{'settings__content--disabled': !server_settings.notification.telegram_notification_enabled}">
                <div class="settings__item">
                    <div class="settings__item-heading">Bot トークン</div>
                    <div class="settings__item-label">
                        @BotFather から取得した Bot トークンを入力してください。<br>
                        形式の例: <code>1234567890:ABCDefgh-ijklMNOPqrstUVWXyz</code>
                    </div>
                    <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                        :density="is_form_dense ? 'compact' : 'default'"
                        :type="show_bot_token ? 'text' : 'password'"
                        :append-inner-icon="show_bot_token ? 'mdi-eye-off' : 'mdi-eye'"
                        placeholder="1234567890:ABCDefgh..."
                        v-model="server_settings.notification.telegram_bot_token"
                        @click:append-inner="show_bot_token = !show_bot_token"
                        @update:modelValue="onSettingChanged()" />
                </div>
                <div class="settings__item">
                    <div class="settings__item-heading">チャット ID</div>
                    <div class="settings__item-label">
                        通知の送信先となるチャット ID またはチャンネル名を入力してください。<br>
                        個人チャット: <code>123456789</code> / グループ: <code>-1001234567890</code> / チャンネル: <code>@mychannel</code>
                    </div>
                    <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                        :density="is_form_dense ? 'compact' : 'default'"
                        placeholder="-1001234567890"
                        v-model="server_settings.notification.telegram_chat_id"
                        @update:modelValue="onSettingChanged()" />
                </div>
                <div class="settings__item">
                    <div class="settings__item-heading">公開ベース URL (オプション)</div>
                    <div class="settings__item-label">
                        通知メッセージに「再生」ボタンを追加する場合は、KonomiTV の公開 URL を入力してください。<br>
                        空欄にすると再生ボタンは表示されません。末尾のスラッシュは不要です。<br>
                        例: <code>https://konomi.example.com</code>
                    </div>
                    <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                        :density="is_form_dense ? 'compact' : 'default'"
                        placeholder="https://konomi.example.com"
                        v-model="server_settings.notification.telegram_base_url"
                        @update:modelValue="onSettingChanged()" />
                </div>
                <div class="settings__item">
                    <div class="settings__item-heading">通知メッセージのカスタムテンプレート (オプション)</div>
                    <div class="settings__item-label">
                        通知メッセージの本文をカスタマイズできます。空欄の場合はデフォルトの形式が使用されます。<br>
                        テンプレートは Telegram の <strong>HTML モード</strong>で送信されます (<code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;a href="..."&gt;</code> などが使用可能)。<br>
                        以下の変数が使用できます:<br>
                        <code>{title}</code> 番組タイトル &nbsp;
                        <code>{channel}</code> チャンネル名 &nbsp;
                        <code>{start_time}</code> 放送開始時刻 &nbsp;
                        <code>{end_time}</code> 放送終了時刻 &nbsp;
                        <code>{duration}</code> 放送時間(分) &nbsp;
                        <code>{description}</code> 番組概要 &nbsp;
                        <code>{file_size}</code> 録画サイズ
                    </div>
                    <v-textarea class="settings__item-form" color="primary" variant="outlined" hide-details
                        :density="is_form_dense ? 'compact' : 'default'"
                        :rows="is_form_dense ? 5 : 7"
                        :placeholder="default_template_placeholder"
                        v-model="server_settings.notification.telegram_notification_template"
                        @update:modelValue="onTemplateChanged()" />
                    <!-- テンプレートプレビュー表示エリア -->
                    <div v-if="template_preview !== null" class="template-preview mt-3">
                        <div class="template-preview__heading">
                            <Icon icon="mdi:eye" width="16px" class="mr-1" />プレビュー (サンプルデータで展開)
                        </div>
                        <pre class="template-preview__body">{{ template_preview }}</pre>
                    </div>
                    <!-- テンプレートプレビューボタン -->
                    <v-btn class="settings__save-button mt-3" variant="outlined"
                        :loading="is_validating_template"
                        :disabled="!server_settings.notification.telegram_notification_template"
                        @click="previewTemplate()">
                        <Icon icon="mdi:eye" class="mr-2" height="19px" />テンプレートをプレビュー
                    </v-btn>
                </div>
                <v-divider class="mt-6" />
                <div class="settings__item">
                    <div class="settings__item-heading">テスト通知を送信</div>
                    <div class="settings__item-label">
                        上記の設定が正しく動作するか確認するためのテストメッセージを送信します。<br>
                        先に設定を保存してから実行してください。
                    </div>
                </div>
                <v-btn class="settings__save-button mt-4" variant="flat"
                    :loading="is_sending_test"
                    :disabled="!server_settings.notification.telegram_bot_token || !server_settings.notification.telegram_chat_id"
                    @click="sendTestNotification()">
                    <Icon icon="mdi:send" class="mr-2" height="19px" />テスト通知を送信
                </v-btn>
            </div>
        </div>
        <!-- 設定保存ボタン -->
        <div class="settings__content mt-6">
            <v-btn class="settings__save-button" color="primary" variant="flat"
                :loading="is_saving"
                @click="saveSettings()">
                <Icon icon="fluent:save-16-filled" class="mr-2" height="19px" />設定を保存
            </v-btn>
        </div>
    </SettingsBase>
</template>
<script lang="ts">

import { defineComponent } from 'vue';

import Message from '@/message';
import Settings, { IServerSettings, IServerSettingsDefault } from '@/services/Settings';
import Utils from '@/utils';
import SettingsBase from '@/views/Settings/Base.vue';

export default defineComponent({
    name: 'Settings-Notification',
    components: {
        SettingsBase,
    },
    data() {
        return {
            // ユーティリティをテンプレートで使えるように
            Utils: Object.freeze(Utils),

            // フォームを小さくするかどうか
            is_form_dense: Utils.isSmartphoneHorizontal(),

            // サーバー設定 (読み込み完了前はデフォルト値を使用)
            server_settings: IServerSettingsDefault as IServerSettings,

            // Bot トークンの表示/非表示フラグ
            show_bot_token: false,

            // 設定保存中フラグ
            is_saving: false,

            // テスト通知送信中フラグ
            is_sending_test: false,

            // テンプレート検証中フラグ
            is_validating_template: false,

            // テンプレートプレビューテキスト (null = 未取得 or テンプレート変更後リセット)
            template_preview: null as string | null,

            // 設定が変更されたかどうかのフラグ (未保存の変更があることを追跡する)
            is_dirty: false,

            // カスタムテンプレートのプレースホルダー (デフォルト形式のサンプルを表示する)
            default_template_placeholder: (
                '📺 <b>{title}</b>\n' +
                '📡 {channel}  |  🕐 {start_time}〜{end_time} ({duration}分)\n' +
                '📝 {description}\n' +
                '💾 録画サイズ: {file_size}'
            ),
        };
    },
    async created() {
        // サーバー設定を取得する
        const settings = await Settings.fetchServerSettings();
        if (settings !== null) {
            this.server_settings = settings;
        }
    },
    methods: {
        /** 設定フィールドが変更されたときに呼ばれる (未保存フラグを立てる) */
        onSettingChanged() {
            this.is_dirty = true;
        },

        /** テンプレートフィールドが変更されたときに呼ばれる (プレビューをリセットして未保存フラグを立てる) */
        onTemplateChanged() {
            this.is_dirty = true;
            // テンプレート内容が変わったらプレビューをリセットして再取得を促す
            this.template_preview = null;
        },

        /** 設定を保存する */
        async saveSettings() {
            this.is_saving = true;
            try {
                const success = await Settings.updateServerSettings(this.server_settings);
                if (success) {
                    this.is_dirty = false;
                    Message.success('通知設定を保存しました。');
                }
            } finally {
                this.is_saving = false;
            }
        },

        /** テスト通知を送信する */
        async sendTestNotification() {
            if (this.is_dirty) {
                Message.warning('設定に未保存の変更があります。先に保存してからテスト通知を送信してください。');
                return;
            }
            this.is_sending_test = true;
            try {
                const success = await Settings.sendTestTelegramNotification();
                if (success) {
                    Message.success('テスト通知を送信しました。Telegram を確認してください。');
                }
            } finally {
                this.is_sending_test = false;
            }
        },

        /** テンプレートをサンプルデータでプレビューする */
        async previewTemplate() {
            const template = this.server_settings.notification.telegram_notification_template;
            if (!template) return;
            this.is_validating_template = true;
            try {
                const preview = await Settings.validateTelegramTemplate(template);
                if (preview !== null) {
                    this.template_preview = preview;
                    Message.success('テンプレートの書式は正しいです。');
                }
            } finally {
                this.is_validating_template = false;
            }
        },
    },
});

</script>
<style lang="scss" scoped>

.template-preview {
    border: 1px solid rgb(var(--v-theme-on-surface), 0.2);
    border-radius: 4px;
    padding: 12px 14px;
    background: rgb(var(--v-theme-surface-variant), 0.4);

    &__heading {
        display: flex;
        align-items: center;
        font-size: 12px;
        color: rgb(var(--v-theme-on-surface), 0.6);
        margin-bottom: 8px;
    }

    &__body {
        font-size: 13px;
        line-height: 1.6;
        white-space: pre-wrap;
        word-break: break-word;
        font-family: inherit;
        margin: 0;
    }
}

</style>
