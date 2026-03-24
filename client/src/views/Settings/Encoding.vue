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
            <div class="settings__content-heading mt-6">
                <Icon icon="fluent:settings-20-filled" width="22px" />
                <span class="ml-2">デフォルトのエンコード設定</span>
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">利用するエンコーダー</div>
                <div class="settings__item-label">
                    エンコードキューに追加する際のデフォルトのエンコーダーを設定します。<br>
                    タスク追加時に個別に変更することも可能です。<br>
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="[
                        {title: 'FFmpeg : ソフトウェアエンコーダー', value: 'FFmpeg'},
                        {title: 'QSVEncC : Intel Graphics 搭載 CPU / Intel Arc GPU で利用可能', value: 'QSVEncC'},
                        {title: 'NVEncC : NVIDIA GPU で利用可能', value: 'NVEncC'},
                        {title: 'VCEEncC : AMD GPU で利用可能', value: 'VCEEncC'},
                        {title: 'rkmppenc : Rockchip RK3588 系 SoC 搭載 SBC で利用可能', value: 'rkmppenc'},
                    ]"
                    v-model="server_settings.encoding.default_encoder_type" />
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">映像コーデック</div>
                <div class="settings__item-label">
                    エンコードに使用する映像コーデックを選択します。<br>
                    H.265 は H.264 よりも高い圧縮効率を持ちますが、エンコード速度が遅くなります。<br>
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="['H.264', 'H.265']"
                    v-model="server_settings.encoding.default_video_codec" />
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">品質プリセット</div>
                <div class="settings__item-label">
                    FFmpeg のエンコード速度プリセットを設定します。<br>
                    slower / slow は品質が高くなりますが、エンコード速度が遅くなります。<br>
                </div>
                <v-select class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    :items="['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']"
                    v-model="server_settings.encoding.default_quality_preset" />
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">映像ビットレート</div>
                <div class="settings__item-label">
                    エンコード後の映像ビットレートを設定します。<br>
                    例: 4000k (4Mbps)、8000k (8Mbps) など。<br>
                </div>
                <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    placeholder="4000k"
                    v-model="server_settings.encoding.default_video_bitrate" />
            </div>
            <div class="settings__item">
                <div class="settings__item-heading">音声ビットレート</div>
                <div class="settings__item-label">
                    エンコード後の音声ビットレートを設定します。<br>
                    例: 192k (192kbps)、256k (256kbps) など。<br>
                </div>
                <v-text-field class="settings__item-form" color="primary" variant="outlined" hide-details
                    :density="is_form_dense ? 'compact' : 'default'"
                    placeholder="192k"
                    v-model="server_settings.encoding.default_audio_bitrate" />
            </div>
            <div class="settings__content-heading mt-6">
                <Icon icon="fluent:cut-20-filled" width="22px" />
                <span class="ml-2">CM カット</span>
            </div>
            <div class="settings__item settings__item--switch">
                <div class="settings__item-heading">デフォルトで CM カットを有効にする</div>
                <div class="settings__item-label">
                    エンコードキューに追加する際に、デフォルトで CM (広告) 区間を自動的にカットします。<br>
                    CM 区間の検出はメタデータ解析時に自動的に行われ、検出済みの CM 区間情報が利用されます。<br>
                    CM 区間が検出されていない録画ファイルでは、CM カットはスキップされます。<br>
                </div>
                <v-switch class="settings__item-switch" color="primary" hide-details
                    v-model="server_settings.encoding.default_cm_removal" />
            </div>
            <v-btn class="settings__save-button bg-secondary mt-6" variant="flat" @click="updateServerSettings()">
                <Icon icon="fluent:save-16-filled" class="mr-2" height="23px" />サーバー設定を更新
            </v-btn>
        </div>
    </SettingsBase>
</template>
<script lang="ts" setup>

import { ref } from 'vue';

import Message from '@/message';
import Settings, { IServerSettings, IServerSettingsDefault } from '@/services/Settings';
import useUserStore from '@/stores/UserStore';
import Utils from '@/utils';
import SettingsBase from '@/views/Settings/Base.vue';

// フォームを小さくするかどうか
const is_form_dense = Utils.isSmartphoneHorizontal();

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

// サーバー設定を更新する関数
async function updateServerSettings() {
    const result = await Settings.updateServerSettings(server_settings.value);
    if (result === true) {
        Message.success('サーバー設定を更新しました。\n変更を反映するためには、KonomiTV サーバーを再起動してください。');
    }
}

</script>
