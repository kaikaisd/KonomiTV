<template>
    <Watch :playback_mode="'Video'" />
</template>
<script lang="ts">

import { mapStores } from 'pinia';
import { defineComponent } from 'vue';

import Watch from '@/components/Watch/Watch.vue';
import PlayerController from '@/services/player/PlayerController';
import Videos from '@/services/Videos';
import usePlayerStore, { getActivePlayerController, setActivePlayerController } from '@/stores/PlayerStore';
import useSettingsStore from '@/stores/SettingsStore';

export default defineComponent({
    name: 'Video-Watch',
    components: {
        Watch,
    },
    data() {
        return {
            // ミニプレイヤーからの復帰中かどうか
            // created() で判定し、mounted() で DOM 操作を行うために保持する
            is_restoring_from_mini_player: false,
        };
    },
    computed: {
        ...mapStores(usePlayerStore, useSettingsStore),
    },
    // 開始時に実行
    created() {

        // 下記以外の視聴画面の開始処理は Watch コンポーネントの方で自動的に行われる

        // ミニプレイヤーからの復帰かどうかを判定する
        // ミニプレイヤーで同じ録画番組を再生中であれば、PlayerController を破棄せずにそのまま引き継ぐ
        const existing_controller = getActivePlayerController();
        const mini_player_state = this.playerStore.mini_player_state;
        if (existing_controller && this.playerStore.is_mini_player && mini_player_state &&
            mini_player_state.playback_mode === 'Video' &&
            mini_player_state.video_id === parseFloat(this.$route.params.video_id as string)) {

            // ミニプレイヤーから復帰: フラグを立てて mounted() で DOM 操作を行う
            // created() 時点では Watch コンポーネントの DOM がまだ存在しないため、
            // DPlayer の DOM 要素を視聴画面に戻す操作は mounted() まで遅延させる必要がある
            this.is_restoring_from_mini_player = true;
            return;
        }

        // ミニプレイヤーが別の番組または別のモードで再生中の場合は、先にミニプレイヤーを閉じる
        if (this.playerStore.is_mini_player) {
            this.playerStore.closeMiniPlayer();
        }

        // 再生セッションを初期化
        this.init();
    },
    // DOM がマウントされた後に実行
    mounted() {
        // ミニプレイヤーからの復帰時: DOM が準備できたので DPlayer の DOM 要素を視聴画面に戻す
        if (this.is_restoring_from_mini_player) {
            this.playerStore.restoreFromMiniPlayer();
            this.is_restoring_from_mini_player = false;
        }
    },
    // チャンネル切り替え時に実行
    // コンポーネント（インスタンス）は再利用される
    // ref: https://v3.router.vuejs.org/ja/guide/advanced/navigation-guards.html#%E3%83%AB%E3%83%BC%E3%83%88%E5%8D%98%E4%BD%8D%E3%82%AB%E3%82%99%E3%83%BC%E3%83%88%E3%82%99
    beforeRouteUpdate(to, from, next) {

        // 前の再生セッションを破棄して終了し、完了を待ってから再度初期化する
        const destroy_promise = this.destroy();
        destroy_promise.then(() => this.init());

        // 次のルートに置き換え
        next();
    },
    // 終了前に実行
    beforeUnmount() {

        // ミニプレイヤーモードに移行中の場合は、PlayerController を破棄せずに保持する
        // DPlayer の DOM 要素は既に minimizePlayer() で永続コンテナに退避済みなので、ここでは破棄しない
        if (this.playerStore.is_mini_player) {
            return;
        }

        // destroy() を実行
        // 別のページへ遷移するため、DPlayer のインスタンスを確実に破棄する
        // さもなければ、ブラウザがリロードされるまでバックグラウンドで永遠に再生され続けてしまう
        this.destroy();

        // 上記以外の視聴画面の終了処理は Watch コンポーネントの方で自動的に行われる
    },
    methods: {

        // 再生セッションを初期化する
        async init() {

            // URL 上の録画番組 ID が未定義なら実行しない (フェイルセーフ)
            // 基本あり得ないはずだが、念のため
            if (this.$route.params.video_id === undefined) {
                this.$router.push({path: '/not-found/'});
                return;
            }

            // 録画番組情報を更新する
            const recorded_program = await Videos.fetchVideo(parseFloat(this.$route.params.video_id as string));
            if (recorded_program === null) {
                this.$router.push({path: '/not-found/'});
                return;
            }
            this.playerStore.recorded_program = recorded_program;

            // PlayerController を初期化し、グローバル参照にも設定する
            const controller = new PlayerController('Video');
            setActivePlayerController(controller);
            await controller.init();
        },

        // 再生セッションを破棄する
        // 再生する録画番組を切り替える際にも実行される
        async destroy() {

            // PlayerController を破棄
            const controller = getActivePlayerController();
            if (controller !== null) {
                await controller.destroy();
                setActivePlayerController(null);
            }
        }
    }
});

</script>
