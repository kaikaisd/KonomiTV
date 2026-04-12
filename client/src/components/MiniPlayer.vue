<template>
    <!-- YouTube 風ミニプレイヤー: 視聴画面から他のページに遷移しても画面右下に小さなプレイヤーを表示し続ける -->
    <transition name="mini-player-transition">
        <div v-if="playerStore.is_mini_player && playerStore.mini_player_state" class="mini-player"
            :class="{'mini-player--dragging': is_dragging}">
            <!-- プレイヤー映像エリア: クリックで視聴画面に戻る -->
            <div class="mini-player__video" @click="maximize">
                <!-- DPlayer の映像は #mini-player-persistent-container から CSS で表示される -->
                <div class="mini-player__video-container" ref="videoContainer"></div>
                <!-- ホバー時のオーバーレイ -->
                <div class="mini-player__video-overlay">
                    <Icon icon="fluent:arrow-maximize-20-filled" width="28px" />
                </div>
            </div>
            <!-- 情報バー: チャンネルロゴ・タイトル・コントロールボタン -->
            <div class="mini-player__info">
                <img v-if="playerStore.mini_player_state.channel_id" class="mini-player__logo"
                    :src="`${Utils.api_base_url}/channels/${playerStore.mini_player_state.channel_id}/logo`"
                    @click="maximize">
                <span class="mini-player__title" @click="maximize">
                    {{ playerStore.mini_player_state.title }}
                </span>
                <div class="mini-player__controls">
                    <!-- 再生/一時停止ボタン -->
                    <button class="mini-player__button" @click="togglePlayPause"
                        v-ftooltip.top="playerStore.is_video_paused ? '再生' : '一時停止'">
                        <Icon :icon="playerStore.is_video_paused ? 'fluent:play-20-filled' : 'fluent:pause-20-filled'" width="22px" />
                    </button>
                    <!-- 閉じるボタン -->
                    <button class="mini-player__button" @click="close" v-ftooltip.top="'閉じる'">
                        <Icon icon="fluent:dismiss-20-filled" width="22px" />
                    </button>
                </div>
            </div>
        </div>
    </transition>
</template>
<script setup lang="ts">

import { ref, watch, nextTick, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';

import usePlayerStore, { getActivePlayerController } from '@/stores/PlayerStore';
import Utils from '@/utils';

// ストアとルーターの初期化
const playerStore = usePlayerStore();
const router = useRouter();

// テンプレート参照
const videoContainer = ref<HTMLDivElement | null>(null);

// ドラッグ状態
const is_dragging = ref(false);

/**
 * ミニプレイヤーがアクティブになったとき、永続コンテナ内の DPlayer 映像をミニプレイヤーの映像エリアに表示する
 * DPlayer の DOM 要素自体は #mini-player-persistent-container に保持されているため、
 * ここではそのコンテナをミニプレイヤーの映像エリア内に移動して表示させる
 */
watch(() => playerStore.is_mini_player, async (is_active) => {
    if (is_active) {
        await nextTick();
        const persistent_container = document.getElementById('mini-player-persistent-container');
        if (persistent_container && videoContainer.value) {
            videoContainer.value.appendChild(persistent_container);
            persistent_container.style.display = 'block';
        }
    }
});

/**
 * ミニプレイヤーを最大化して元の視聴画面に戻る
 */
const maximize = () => {
    const state = playerStore.mini_player_state;
    if (!state) return;

    // 永続コンテナを一旦ミニプレイヤーから外して body 直下に戻す (Watch コンポーネントが復帰時にここから取得する)
    const persistent_container = document.getElementById('mini-player-persistent-container');
    if (persistent_container) {
        persistent_container.style.display = 'none';
        document.body.appendChild(persistent_container);
    }

    // 元の視聴画面ルートに遷移
    router.push({ path: state.route_path });
};

/**
 * 再生/一時停止を切り替える
 */
const togglePlayPause = () => {
    const controller = getActivePlayerController();
    if (!controller) return;

    // DPlayer の video 要素を取得して再生/一時停止を切り替え
    const video = document.querySelector<HTMLVideoElement>('.watch-player__dplayer video');
    if (video) {
        if (video.paused) {
            video.play();
            playerStore.is_video_paused = false;
        } else {
            video.pause();
            playerStore.is_video_paused = true;
        }
    }
};

/**
 * ミニプレイヤーを閉じて再生を完全に停止する
 */
const close = async () => {
    // 永続コンテナを body 直下に戻す
    const persistent_container = document.getElementById('mini-player-persistent-container');
    if (persistent_container) {
        persistent_container.style.display = 'none';
        document.body.appendChild(persistent_container);
    }

    await playerStore.closeMiniPlayer();
};

// コンポーネント破棄時のクリーンアップ
onUnmounted(() => {
    is_dragging.value = false;
});

</script>
<style lang="scss" scoped>

.mini-player {
    position: fixed;
    right: 24px;
    bottom: 24px;
    width: 400px;
    background: rgb(var(--v-theme-background-lighten-1));
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.3);
    z-index: 9999;
    overflow: hidden;
    transition: box-shadow 0.2s ease;

    &:hover {
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5), 0 4px 12px rgba(0, 0, 0, 0.4);
    }

    @include smartphone-horizontal {
        width: 320px;
        right: 16px;
        bottom: 16px;
    }
    @include smartphone-vertical {
        width: calc(100% - 24px);
        right: 12px;
        bottom: calc(env(safe-area-inset-bottom) + 64px);  // ボトムナビゲーションバーの上
    }

    .mini-player__video {
        position: relative;
        width: 100%;
        aspect-ratio: 16 / 9;
        background: rgb(var(--v-theme-black));
        cursor: pointer;
        overflow: hidden;

        // DPlayer の映像を表示するコンテナ
        .mini-player__video-container {
            width: 100%;
            height: 100%;

            // #mini-player-persistent-container 内の DPlayer をミニプレイヤーサイズにフィットさせる
            :deep(#mini-player-persistent-container) {
                width: 100%;
                height: 100%;

                .watch-player__dplayer {
                    width: 100% !important;
                    height: 100% !important;

                    .dplayer-video-wrap {
                        width: 100%;
                        height: 100%;
                    }

                    // ミニプレイヤーモードでは DPlayer のコントロール UI を非表示にする
                    .dplayer-controller,
                    .dplayer-controller-mask,
                    .dplayer-notice,
                    .dplayer-info-panel,
                    .dplayer-comment-box,
                    .dplayer-comment-setting-box,
                    .dplayer-setting-box,
                    .dplayer-mobile-icon-wrap {
                        display: none !important;
                    }

                    // コメント (弾幕) はミニプレイヤーでも表示する
                    .dplayer-danmaku {
                        font-size: 60% !important;
                    }
                }
            }
        }

        // ホバー時のオーバーレイ (最大化アイコン)
        .mini-player__video-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(0, 0, 0, 0.35);
            color: rgb(var(--v-theme-text));
            opacity: 0;
            transition: opacity 0.2s ease;
        }

        &:hover .mini-player__video-overlay {
            opacity: 1;
        }
    }

    .mini-player__info {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 8px 8px 12px;

        .mini-player__logo {
            flex-shrink: 0;
            width: 44px;
            height: 26px;
            border-radius: 4px;
            background: linear-gradient(150deg, rgb(var(--v-theme-gray)), rgb(var(--v-theme-background-lighten-2)));
            object-fit: cover;
            cursor: pointer;
            user-select: none;
        }

        .mini-player__title {
            flex: 1;
            font-size: 13px;
            font-weight: 500;
            line-height: 1.4;
            color: rgb(var(--v-theme-text));
            cursor: pointer;
            overflow: hidden;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;

            &:hover {
                color: rgb(var(--v-theme-primary));
            }
        }

        .mini-player__controls {
            display: flex;
            align-items: center;
            gap: 2px;
            flex-shrink: 0;
        }

        .mini-player__button {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            border: none;
            border-radius: 50%;
            background: transparent;
            color: rgb(var(--v-theme-text));
            cursor: pointer;
            transition: background-color 0.15s ease;

            &:hover {
                background: rgba(var(--v-theme-text), 0.1);
            }
        }
    }
}

// 表示/非表示のトランジション
.mini-player-transition-enter-active {
    transition: transform 0.3s cubic-bezier(0.22, 0.61, 0.36, 1), opacity 0.3s ease;
}
.mini-player-transition-leave-active {
    transition: transform 0.2s cubic-bezier(0.55, 0.06, 0.68, 0.19), opacity 0.2s ease;
}
.mini-player-transition-enter-from {
    transform: translateY(100%) scale(0.8);
    opacity: 0;
}
.mini-player-transition-leave-to {
    transform: translateY(100%) scale(0.8);
    opacity: 0;
}

</style>
