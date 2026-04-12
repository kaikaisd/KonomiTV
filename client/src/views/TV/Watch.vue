<template>
    <Watch :playback_mode="'Live'" />
</template>
<script lang="ts">

import { mapStores } from 'pinia';
import { defineComponent } from 'vue';

import Watch from '@/components/Watch/Watch.vue';
import PlayerController from '@/services/player/PlayerController';
import useChannelsStore from '@/stores/ChannelsStore';
import usePlayerStore, { getActivePlayerController, setActivePlayerController } from '@/stores/PlayerStore';
import useSettingsStore from '@/stores/SettingsStore';
import Utils from '@/utils';

export default defineComponent({
    name: 'TV-Watch',
    components: {
        Watch,
    },
    data() {
        return {
            // インターバル ID
            // ページ遷移時に setInterval(), setTimeout() の実行を止めるのに使う
            // setInterval(), setTimeout() の返り値を登録する
            interval_ids: [] as number[],
            // ミニプレイヤーからの復帰中かどうか
            // created() で判定し、mounted() で DOM 操作を行うために保持する
            is_restoring_from_mini_player: false,
        };
    },
    computed: {
        ...mapStores(useChannelsStore, usePlayerStore, useSettingsStore),
    },
    // 開始時に実行
    created() {

        // 下記以外の視聴画面の開始処理は Watch コンポーネントの方で自動的に行われる

        // チャンネル ID をセット
        this.channelsStore.display_channel_id = this.$route.params.display_channel_id as string;

        // ミニプレイヤーからの復帰かどうかを判定する
        // ミニプレイヤーで同じチャンネルを再生中であれば、PlayerController を破棄せずにそのまま引き継ぐ
        const existing_controller = getActivePlayerController();
        const mini_player_state = this.playerStore.mini_player_state;
        if (existing_controller && this.playerStore.is_mini_player && mini_player_state &&
            mini_player_state.playback_mode === 'Live' &&
            mini_player_state.channel_id === this.$route.params.display_channel_id) {

            // ミニプレイヤーから復帰: フラグを立てて mounted() で DOM 操作を行う
            // created() 時点では Watch コンポーネントの DOM がまだ存在しないため、
            // DPlayer の DOM 要素を視聴画面に戻す操作は mounted() まで遅延させる必要がある
            this.is_restoring_from_mini_player = true;

            // チャンネル情報の定期更新タイマーを再開する
            this.startChannelUpdateTimers();
            return;
        }

        // ミニプレイヤーが別のチャンネルまたは別のモードで再生中の場合は、先にミニプレイヤーを��じる
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

        // 前の再生セッションを破棄して終了する
        // このとき this.interval_ids に登録された setTimeout がキャンセルされるため、
        // 後述の 0.5 秒の間にザッピングにより他のチャンネルに切り替えた場合は this.init() は実行されない
        const destroy_promise = this.destroy();

        // チャンネル ID を次のチャンネルのものに切り替える
        this.channelsStore.display_channel_id = to.params.display_channel_id as string;

        (async () => {

            // ザッピング（「前/次のチャンネル」ボタン or 上下キーショートカット）によるチャンネル移動時のみ、
            // 0.5秒だけ待ってから新しい再生セッションを初期化する
            // 連続してチャンネルを切り替えた際に毎回再生処理を開始しないように猶予を設ける
            if (this.playerStore.is_zapping === true) {
                this.playerStore.is_zapping = false;
                this.interval_ids.push(window.setTimeout(() => {
                    destroy_promise.then(() => this.init());  // destroy() の実行完了を待ってから初期化する
                }, 0.5 * 1000));

            // 通常のチャンネル移動時は、すぐに再生セッションを初期化する
            } else {
                destroy_promise.then(() => this.init());  // destroy() の実行完了を待ってから初期化する
            }
        })();

        // 次のルートに置き換え
        next();
    },
    // 終了前に実行
    beforeUnmount() {

        // ミニプレイヤーモードに移行中の場合は、PlayerController を破棄せずに保持する
        // DPlayer の DOM 要素は既に minimizePlayer() で永続コンテナに退避済みなので、ここでは破棄しない
        if (this.playerStore.is_mini_player) {
            // タイマーだけは停止する (チャンネル情報の定期更新はミニプレイヤーでは不要)
            for (const interval_id of this.interval_ids) {
                window.clearInterval(interval_id);
            }
            this.interval_ids = [];
            return;
        }

        // destroy() を実行
        // 別のページへ遷移するため、DPlayer のインスタンスを確実に破棄する
        // さもなければ、ブラウザがリロードされるまでバックグラウンドで永遠に再生され続けてしまう
        this.destroy();

        // このページから離れるので、チャンネル ID を gr000 (ダミー値) に戻す
        this.channelsStore.display_channel_id = 'gr000';

        // 上記以外の視聴画面の終了処理は Watch コンポーネントの方で自動的に行われる
    },
    methods: {

        // チャンネル情報の定期更新タイマーを開始する
        // ミニプレイヤーからの復帰時にも使用する
        startChannelUpdateTimers() {
            // 00秒までの残り秒数を取得
            const residue_second = 60 - new Date().getSeconds();

            // 00秒になるまで待ってから実行するタイマー
            this.interval_ids.push(window.setTimeout(() => {
                this.channelsStore.update(true);
                // 以降、30秒おきにチャンネル情報を更新
                this.interval_ids.push(window.setInterval(() => {
                    this.channelsStore.update(true);
                }, 30 * 1000));
            }, residue_second * 1000));
        },

        // 再生セッションを初期化する
        async init() {

            // チャンネル情報の定期更新タイマーを開始
            this.startChannelUpdateTimers();

            // チャンネル情報を更新 (初回)
            await this.channelsStore.update();

            // URL 上のチャンネル ID が未定義なら実行しない (フェイルセーフ)
            // 基本あり得ないはずだが、念のため
            if (this.$route.params.display_channel_id === undefined) {
                this.$router.push({path: '/not-found/'});
                return;
            }

            // もしこの時点でチャンネル名が「チャンネル情報取得エラー」の場合、
            // URL で指定された display_channel_id に紐づくチャンネル情報がないことを示しているので、404 ページにリダイレクト
            if (this.channelsStore.channel.current.name === 'チャンネル情報取得エラー') {
                await Utils.sleep(3);  // 3秒待機
                this.$router.push({path: '/not-found/'});
                return;
            }

            // PlayerController を初期化し、グローバル参照にも設定する
            const controller = new PlayerController('Live');
            setActivePlayerController(controller);
            await controller.init();
        },

        // 再生セッションを破棄する
        // チャンネルを切り替える際に実行される
        async destroy() {

            // clearInterval() ですべての setInterval(), setTimeout() の実行を止める
            // clearInterval() と clearTimeout() は中身共通なので問題ない
            for (const interval_id of this.interval_ids) {
                window.clearInterval(interval_id);
            }

            // interval_ids をクリア
            this.interval_ids = [];

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
