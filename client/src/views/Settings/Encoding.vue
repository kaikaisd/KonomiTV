<template>
    <!-- ベース画面の中にそれぞれの設定画面で異なる部分を記述する -->
    <SettingsBase>
        <h2 class="settings__heading">
            <a v-ripple class="settings__back-button" @click="$router.back()">
                <Icon icon="fluent:chevron-left-12-filled" width="27px" />
            </a>
            <Icon icon="fluent:video-clip-multiple-16-filled" width="22px" />
            <span class="ml-2">エンコード設定</span>
        </h2>
        <div class="settings__description">
            エンコード設定を変更するには、管理者アカウントでログインしている必要があります。<br>
        </div>
        <div class="settings__description mt-1">
            [サーバー設定を更新] ボタンを押さずにこのページから離れると、変更内容は破棄されます。<br>
            変更を反映するには KonomiTV サーバーの再起動が必要です。<br>
        </div>
        <div class="settings__content" :class="{'settings__content--disabled': is_disabled}">
            <!-- 出力先セクション -->
            <div class="settings__content-heading">
                <Icon icon="fluent:folder-open-20-filled" width="22px" />
                <span class="ml-2">出力先</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">エンコード後のファイルの出力先フォルダ</div>
                <div class="settings__item-label">
                    エンコードされたファイルの保存先フォルダの絶対パスを指定します。<br>
                    空欄の場合は、元の録画ファイルと同じフォルダに出力されます。<br>
                </div>
                <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    placeholder="例: E:\TV-Encoded"
                    v-model="server_settings.encoding.output_directory" />
            </div>

            <!-- デフォルトプロファイルセクション -->
            <div class="settings__content-heading mt-6">
                <Icon icon="fluent:checkmark-circle-20-filled" width="22px" />
                <span class="ml-2">デフォルトプロファイル</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">エンコードキュー追加時に使用するデフォルトプロファイル</div>
                <div class="settings__item-label">
                    録画番組カードからエンコードキューに追加する際に、初期選択されるプロファイルを設定します。<br>
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="profileNames"
                    v-model="server_settings.encoding.default_profile_name" />
            </div>

            <!-- エンコードプロファイル一覧セクション -->
            <div class="settings__content-heading mt-6">
                <Icon icon="fluent:list-20-filled" width="22px" />
                <span class="ml-2">エンコードプロファイル</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-label">
                    エンコードプロファイルには、エンコーダー・コーデック・ビットレート・CM カットなどの設定をまとめて保存できます。<br>
                    Amatsukaze のエンコードプロファイルと同様に、用途に応じて複数のプロファイルを作成できます。<br>
                </div>
            </div>

            <!-- プロファイルカード -->
            <v-card v-for="(profile, index) in server_settings.encoding.profiles" :key="'profile-' + index"
                class="encoding-profile-card mb-4" variant="outlined">
                <v-card-text class="pa-4">
                    <!-- プロファイル名 -->
                    <div class="d-flex align-center mb-3">
                        <v-text-field color="primary" variant="outlined" hide-details density="compact"
                            label="プロファイル名"
                            v-model="profile.name" />
                        <button v-ripple class="settings__item-delete-button ml-2"
                            @click="removeProfile(index)">
                            <svg class="iconify iconify--fluent" width="20px" height="20px" viewBox="0 0 16 16">
                                <path fill="currentColor" d="M7 3h2a1 1 0 0 0-2 0ZM6 3a2 2 0 1 1 4 0h4a.5.5 0 0 1 0 1h-.564l-1.205 8.838A2.5 2.5 0 0 1 9.754 15H6.246a2.5 2.5 0 0 1-2.477-2.162L2.564 4H2a.5.5 0 0 1 0-1h4Zm1 3.5a.5.5 0 0 0-1 0v5a.5.5 0 0 0 1 0v-5ZM9.5 6a.5.5 0 0 0-.5.5v5a.5.5 0 0 0 1 0v-5a.5.5 0 0 0-.5-.5Z"></path>
                            </svg>
                        </button>
                    </div>
                    <!-- エンコーダー -->
                    <div class="mb-3">
                        <v-select color="primary" variant="outlined" hide-details density="compact"
                            label="エンコーダー"
                            :items="encoderTypeItems"
                            v-model="profile.encoder_type" />
                    </div>
                    <!-- 映像コーデック -->
                    <div class="mb-3">
                        <v-select color="primary" variant="outlined" hide-details density="compact"
                            label="映像コーデック"
                            :items="['H.264', 'H.265']"
                            v-model="profile.video_codec" />
                    </div>
                    <!-- 品質プリセット -->
                    <div class="mb-3">
                        <v-select color="primary" variant="outlined" hide-details density="compact"
                            label="品質プリセット"
                            :items="['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']"
                            v-model="profile.quality_preset" />
                    </div>
                    <!-- 映像ビットレート / 音声ビットレート (横並び) -->
                    <div class="d-flex mb-3" style="gap: 12px;">
                        <v-text-field color="primary" variant="outlined" hide-details density="compact"
                            label="映像ビットレート" placeholder="4000k"
                            v-model="profile.video_bitrate" style="flex: 1;" />
                        <v-text-field color="primary" variant="outlined" hide-details density="compact"
                            label="音声ビットレート" placeholder="192k"
                            v-model="profile.audio_bitrate" style="flex: 1;" />
                    </div>
                    <!-- CM カット -->
                    <v-switch color="primary" hide-details density="compact" label="CM カットを有効にする"
                        v-model="profile.cm_removal" />
                </v-card-text>
            </v-card>

            <!-- プロファイル追加ボタン -->
            <v-btn class="mt-2" color="background-lighten-2" variant="flat" height="40px"
                @click="addProfile()">
                <Icon icon="fluent:add-12-filled" height="17px" />
                <span class="ml-1">プロファイルを追加</span>
            </v-btn>

            <v-btn class="settings__save-button bg-secondary mt-6" variant="flat" @click="updateServerSettings()">
                <Icon icon="fluent:save-16-filled" class="mr-2" height="23px" />サーバー設定を更新
            </v-btn>
        </div>
    </SettingsBase>
</template>
<script lang="ts" setup>

import { ref, computed } from 'vue';

import Message from '@/message';
import Settings, { IEncodingProfile, IServerSettings, IServerSettingsDefault } from '@/services/Settings';
import useUserStore from '@/stores/UserStore';
import Utils from '@/utils';
import SettingsBase from '@/views/Settings/Base.vue';

// フォームを小さくするかどうか
const is_form_dense = Utils.isSmartphoneHorizontal();

// エンコーダーの選択肢
const encoderTypeItems = [
    {title: 'FFmpeg : ソフトウェアエンコーダー', value: 'FFmpeg'},
    {title: 'QSVEncC : Intel QSV', value: 'QSVEncC'},
    {title: 'NVEncC : NVIDIA NVENC', value: 'NVEncC'},
    {title: 'VCEEncC : AMD VCE', value: 'VCEEncC'},
    {title: 'rkmppenc : Rockchip MPP', value: 'rkmppenc'},
];

// ユーザー情報を取得し、もし管理者権限であれば無効化を解除
const is_disabled = ref(true);
const user_store = useUserStore();
user_store.fetchUser().then((user) => {
    if (user && user.is_admin) {
        is_disabled.value = false;
    }
});

// サーバー設定を取得
const server_settings = ref<IServerSettings>(structuredClone(IServerSettingsDefault));
Settings.fetchServerSettings().then((settings) => {
    if (settings) {
        server_settings.value = settings;
    }
});

// プロファイル名のリスト (デフォルトプロファイル選択用)
const profileNames = computed(() => {
    return server_settings.value.encoding.profiles.map(p => p.name);
});

// 新しいプロファイルを追加する
function addProfile() {
    const newProfile: IEncodingProfile = {
        name: `プロファイル ${server_settings.value.encoding.profiles.length + 1}`,
        encoder_type: 'FFmpeg',
        video_codec: 'H.264',
        quality_preset: 'medium',
        video_bitrate: '4000k',
        audio_bitrate: '192k',
        cm_removal: false,
    };
    server_settings.value.encoding.profiles.push(newProfile);
}

// プロファイルを削除する (最低1つは残す)
function removeProfile(index: number) {
    if (server_settings.value.encoding.profiles.length <= 1) {
        Message.error('プロファイルは最低1つ必要です。');
        return;
    }
    const removedName = server_settings.value.encoding.profiles[index].name;
    server_settings.value.encoding.profiles.splice(index, 1);
    // 削除されたプロファイルがデフォルトだった場合は、最初のプロファイルをデフォルトにする
    if (server_settings.value.encoding.default_profile_name === removedName) {
        server_settings.value.encoding.default_profile_name = server_settings.value.encoding.profiles[0].name;
    }
}

// サーバー設定を更新する関数
async function updateServerSettings() {
    const result = await Settings.updateServerSettings(server_settings.value);
    if (result === true) {
        Message.success('サーバー設定を更新しました。\n変更を反映するためには、KonomiTV サーバーを再起動してください。');
    }
}

</script>
<style lang="scss" scoped>

.encoding-profile-card {
    border-color: rgb(var(--v-theme-background-lighten-2));
    background: rgb(var(--v-theme-background-lighten-1));
}

</style>
