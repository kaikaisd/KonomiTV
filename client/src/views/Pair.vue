<template>
    <main class="pair-page">
        <v-card class="pair-card pa-8" width="100%" max-width="520">
            <v-card-title class="text-h5 font-weight-bold">端末を連携</v-card-title>
            <v-card-text class="pt-5">
                <template v-if="userStore.is_logged_in">
                    <p>連携したい端末の画面に表示されているコードを入力してください。</p>
                    <v-text-field v-model="formattedCode" class="pair-card__code-input mt-5"
                        label="ペアリングコード" placeholder="ABCD EFGH"
                        autocomplete="one-time-code" autocapitalize="characters" spellcheck="false" autofocus
                        @keydown.enter="approve()" />
                </template>
                <template v-else>
                    この操作には KonomiTV アカウントへのログインが必要です。
                </template>
                <v-alert v-if="message" class="mt-4" :type="is_succeeded ? 'success' : 'error'">{{message}}</v-alert>
            </v-card-text>
            <v-card-actions>
                <v-btn v-if="!userStore.is_logged_in" color="secondary"
                    :to="`/login/?return=${encodeURIComponent($route.fullPath)}`">ログイン</v-btn>
                <v-btn v-else color="secondary" :loading="is_loading" :disabled="code.length !== 8"
                    @click="approve()">この端末を許可</v-btn>
            </v-card-actions>
        </v-card>
    </main>
</template>
<script lang="ts" setup>

import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import DeviceAuth from '@/services/DeviceAuth';
import useUserStore from '@/stores/UserStore';

const route = useRoute();
const userStore = useUserStore();

// 承認対象のユーザーコード (区切り文字を含まない8文字のみを保持する)
// 端末側から渡されたクエリパラメータがあれば初期値として利用する
const code = ref(String(route.query.code ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8));

// 入力欄に表示するユーザーコード
// 端末側の表示と揃えて4文字区切りで見せつつ、内部では区切りを含まない8文字だけを保持する
// これにより、小文字入力や空白・ハイフンを含む貼り付けでも末尾の文字が欠けない
const formattedCode = computed({
    get: () => code.value.length > 4 ? `${code.value.slice(0, 4)} ${code.value.slice(4)}` : code.value,
    set: (value: string) => {
        code.value = value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8);
    },
});

// 承認リクエストの送信中かどうか
const is_loading = ref(false);
// 承認結果のメッセージと成否 (v-alert の表示切り替えに使う)
const message = ref('');
const is_succeeded = ref(false);

onMounted(() => userStore.fetchUser());

// 入力されたユーザーコードをサーバーへ送信し、端末の連携を承認する
async function approve() {
    // コードが8文字揃っていない場合と、送信中の二重操作は受け付けない
    if (code.value.length !== 8 || is_loading.value === true) {
        return;
    }
    is_loading.value = true;
    is_succeeded.value = await DeviceAuth.approve(code.value);
    message.value = is_succeeded.value
        ? '連携しました。連携した端末の画面に戻ってください。'
        : 'コードが無効か、有効期限が切れています。';
    is_loading.value = false;
}

</script>
<style lang="scss" scoped>

.pair-page {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 24px;
}

.pair-card {
    &__code-input :deep(input) {
        font-family: monospace;
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-align: center;
        text-transform: uppercase;
    }
}

</style>
