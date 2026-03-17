<template>
    <div>
        <div class="navigation-container elevation-8" :class="{'navigation-container--icon-only': iconOnly}">
            <nav class="navigation" :class="{'navigation--icon-only': iconOnly}">
                <div class="navigation-scroll" :class="{'navigation-scroll--icon-only': iconOnly}">
                    <router-link v-ripple class="navigation__link" active-class="navigation__link--active" to="/tv/"
                        :class="{
                            'navigation__link--active': $route.path.startsWith('/tv'),
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? 'テレビをみる' : ''">
                        <Icon class="navigation__link-icon" icon="fluent:tv-20-regular" width="26px" />
                        <span v-if="!iconOnly" class="navigation__link-text">テレビをみる</span>
                    </router-link>
                    <router-link v-ripple class="navigation__link" active-class="navigation__link--active" to="/videos/"
                        :class="{
                            'navigation__link--active': $route.path.startsWith('/videos'),
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? 'ビデオをみる' : ''">
                        <Icon class="navigation__link-icon" icon="fluent:movies-and-tv-20-regular" width="26px" />
                        <span v-if="!iconOnly" class="navigation__link-text">ビデオをみる</span>
                    </router-link>
                    <router-link v-ripple class="navigation__link" active-class="navigation__link--active" to="/timetable/"
                        :class="{
                            'navigation__link--active': $route.path.startsWith('/timetable'),
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? '番組表' : ''">
                        <Icon class="navigation__link-icon" icon="fluent:calendar-ltr-20-regular" width="26px" />
                        <span v-if="!iconOnly" class="navigation__link-text">番組表</span>
                    </router-link>
                    <router-link v-ripple class="navigation__link" active-class="navigation__link--active" to="/reservations/"
                        :class="{
                            'navigation__link--active': $route.path.startsWith('/reservations'),
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? '録画予約' : ''">
                        <Icon class="navigation__link-icon" icon="fluent:timer-16-regular" width="26px" style="padding: 0.5px;" />
                        <span v-if="!iconOnly" class="navigation__link-text">録画予約</span>
                    </router-link>
                    <router-link v-ripple class="navigation__link" active-class="navigation__link--active" to="/captures/"
                        :class="{
                            'navigation__link--active': $route.path.startsWith('/captures'),
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? 'キャプチャ' : ''">
                        <Icon class="navigation__link-icon" icon="fluent:image-multiple-24-regular" width="26px" />
                        <span v-if="!iconOnly" class="navigation__link-text">キャプチャ</span>
                    </router-link>
                    <router-link v-ripple class="navigation__link" active-class="navigation__link--active" to="/mylist/"
                        :class="{
                            'navigation__link--active': $route.path.startsWith('/mylist'),
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? 'マイリスト' : ''">
                        <Icon class="navigation__link-icon" icon="ic:round-playlist-play" width="26px" />
                        <span v-if="!iconOnly" class="navigation__link-text">マイリスト</span>
                    </router-link>
                    <router-link v-ripple class="navigation__link" active-class="navigation__link--active" to="/watched-history/"
                        :class="{
                            'navigation__link--active': $route.path.startsWith('/watched-history'),
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? '視聴履歴' : ''">
                        <Icon class="navigation__link-icon" icon="fluent:history-20-regular" width="26px" />
                        <span v-if="!iconOnly" class="navigation__link-text">視聴履歴</span>
                    </router-link>
                    <v-spacer></v-spacer>
                    <router-link v-ripple class="navigation__link" active-class="navigation__link--active" to="/settings/"
                        :class="{
                            'navigation__link--active': $route.path.startsWith('/settings'),
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? '設定' : ''">
                        <Icon class="navigation__link-icon" icon="fluent:settings-20-regular" width="26px" />
                        <span v-if="!iconOnly" class="navigation__link-text">設定</span>
                    </router-link>
                    <!-- Cloudflare Access セッション切れ再認証ボタン: CF セッションが期限切れの場合のみ表示する -->
                    <a v-if="cfSessionExpired" v-ripple class="navigation__link navigation__link--cf-expired"
                        :class="{
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? 'CF Accessセッション切れ: 再認証が必要です' : ''"
                        @click.prevent="reAuthenticate">
                        <Icon class="navigation__link-icon" icon="fluent:key-16-regular" width="22px" />
                        <span v-if="!iconOnly" class="navigation__link-text">CF Access 再認証</span>
                    </a>
                    <!-- Cloudflare Access のログアウトボタン: CF Access 経由でログインしている場合のみ表示する -->
                    <!-- /cdn-cgi/access/logout にリダイレクトすることでセッションを終了する -->
                    <a v-if="isCloudflareAccess" v-ripple class="navigation__link" href="/cdn-cgi/access/logout"
                        :class="{
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ? 'CF Accessからログアウト' : ''">
                        <Icon class="navigation__link-icon" icon="fa:sign-out" width="22px" />
                        <span v-if="!iconOnly" class="navigation__link-text">CF Accessからログアウト</span>
                    </a>
                    <a v-ripple class="navigation__link" active-class="navigation__link--active"
                        href="https://github.com/kaikaisd/KonomiTV" target="_blank"
                        :class="{
                            'navigation__link--develop-version': versionStore.is_client_develop_version,
                            'navigation__link--highlight': versionStore.is_update_available,
                            'navigation__link--icon-only': iconOnly,
                        }"
                        v-ftooltip.right="iconOnly ?
                            (versionStore.is_update_available ? `アップデートがあります (version ${versionStore.latest_version})` : `version ${versionStore.client_version}`) :
                            (versionStore.is_update_available ? `アップデートがあります (version ${versionStore.latest_version})` : '')">
                        <Icon class="navigation__link-icon" icon="fluent:info-16-regular" width="26px" />
                        <span v-if="!iconOnly" class="navigation__link-text">version {{versionStore.client_version}}</span>
                    </a>
                </div>
            </nav>
        </div>
        <BottomNavigation />
    </div>
</template>
<script lang="ts">

import { mapStores } from 'pinia';
import { defineComponent } from 'vue';

import BottomNavigation from '@/components/BottomNavigation.vue';
import useVersionStore from '@/stores/VersionStore';

export default defineComponent({
    name: 'Navigation',
    components: {
        BottomNavigation,
    },
    props: {
        // アイコンのみモード: テキストを非表示にし、幅を縮小する
        // 番組表ページでは番組表の表示領域を広く取るためにこのモードを使用する
        iconOnly: {
            type: Boolean,
            default: false,
        },
    },
    data() {
        return {
            // Cloudflare Access 経由で認証済みかどうか
            // /cdn-cgi/access/get-identity が 200 を返せば認証済みと判断する
            isCloudflareAccess: false,
            // CF Access が存在するが未認証 (セッション切れ) の状態かどうか
            // /cdn-cgi/access/get-identity が 200 以外の HTTP レスポンスを返した場合に true になる。
            // CF Access が導入されていない環境では fetch 自体が失敗するか 404 が返るため false のまま。
            // NOTE: API リクエストが CF Access にブロックされると CORS エラーになりレスポンスが取得できないため、
            //       APIClient 側のレスポンスヘッダー監視ではなく、/cdn-cgi/access/get-identity の HTTP
            //       ステータスコードを直接確認することで確実な検知を実現している。
            cfSessionExpired: false,
        };
    },
    computed: {
        ...mapStores(useVersionStore),
    },
    methods: {
        // CF Access 再認証: ページをリロードして CF Access の認証フローを開始する
        reAuthenticate(): void {
            window.location.reload();
        },
    },
    async created() {
        await this.versionStore.fetchServerVersion();
        // /cdn-cgi/access/get-identity の HTTP ステータスで CF Access の状態を判別する:
        //   200     → CF Access 認証済み: ログアウトボタンを表示する
        //   非200   → CF Access が存在するが未認証: 再認証ボタンを表示する
        //   例外発生 → CF Access なし (LAN 直接アクセス等): どちらも表示しない
        // CF Access が未認証の場合、API リクエストは CF Access のログインページへ CORS リダイレクトされるため
        // Axios のレスポンスオブジェクトが取得できず APIClient 側での検知が不可能。
        // そのためここで fetch() を使って直接確認するのが最も確実な手段となる。
        try {
            const response = await fetch('/cdn-cgi/access/get-identity');
            if (response.ok) {
                // 200: 認証済み
                this.isCloudflareAccess = true;
                this.cfSessionExpired = false;
            } else {
                // 400 / 403 等: CF Access は存在するが未認証
                this.isCloudflareAccess = false;
                this.cfSessionExpired = true;
            }
        } catch {
            // ネットワークエラーまたは CF Access が導入されていない環境
            this.isCloudflareAccess = false;
            this.cfSessionExpired = false;
        }
    }
});

</script>
<style lang="scss" scoped>

.navigation-container {
    flex-shrink: 0;
    width: 220px;  // .navigation を fixed にするため、浮いた分の幅を確保する
    background: rgb(var(--v-theme-background-lighten-1));
    @include smartphone-horizontal {
        width: 210px;
    }
    @include smartphone-horizontal-short {
        width: 190px;
    }
    @include smartphone-vertical {
        display: none;
    }

    // アイコンのみモード: 幅を68pxに縮小
    &--icon-only {
        width: 68px;
        @include smartphone-horizontal {
            width: 60px;
        }
        @include smartphone-horizontal-short {
            width: 56px;
        }
    }

    .navigation {
        position: fixed;
        width: 220px;
        top: 65px;  // ヘッダーの高さ分
        left: 0px;
        // スマホ・タブレットのブラウザでアドレスバーが完全に引っ込むまでビューポートの高さが更新されず、
        // その間下に何も背景がない部分ができてしまうのを防ぐ
        bottom: -100px;
        padding-bottom: 100px;
        background: rgb(var(--v-theme-background-lighten-1));
        z-index: 1;
        @include smartphone-horizontal {
            top: 48px;
            width: 210px;
        }
        @include smartphone-horizontal-short {
            width: 190px;
        }

        // アイコンのみモード: 幅を68pxに縮小
        &--icon-only {
            width: 68px;
            @include smartphone-horizontal {
                width: 60px;
            }
            @include smartphone-horizontal-short {
                width: 56px;
            }
        }

        .navigation-scroll {
            display: flex;
            flex-direction: column;
            height: 100%;
            padding: 22px 12px;
            overflow-x: hidden;
            overflow-y: auto;
            @include smartphone-horizontal {
                padding: 10px 12px;
            }
            @include smartphone-horizontal-short {
                padding: 10px 8px;
            }
            &::-webkit-scrollbar-track {
                background: rgb(var(--v-theme-background-lighten-1));
            }

            // アイコンのみモード: パディングを調整
            &--icon-only {
                padding: 22px 8px;
                align-items: center;
                @include smartphone-horizontal {
                    padding: 10px 6px;
                }
                @include smartphone-horizontal-short {
                    padding: 10px 4px;
                }
            }

            .navigation__link {
                display: flex;
                align-items: center;
                flex-shrink: 0;
                height: 52px;
                padding-left: 16px;
                margin-top: 4px;
                border-radius: 11px;
                font-size: 16px;
                color: rgb(var(--v-theme-text));
                transition: background-color 0.15s;
                text-decoration: none;
                user-select: none;
                @include smartphone-horizontal {
                    height: 40px;
                    padding-left: 12px;
                    border-radius: 9px;
                    font-size: 15px;
                }

                &:hover {
                    background: rgb(var(--v-theme-background-lighten-2));
                }
                &:first-of-type {
                    margin-top: 0;
                }
                &--active {
                    color: rgb(var(--v-theme-primary));
                    background: rgba(var(--v-theme-primary), 0.15);
                    &:hover {
                        background: rgba(var(--v-theme-primary), 0.15);
                    }
                }
                &--highlight {
                    color: rgb(var(--v-theme-secondary-lighten-1));
                }
                // CF Access セッション切れ: エラー色で強調表示する
                &--cf-expired {
                    color: rgb(var(--v-theme-error));
                    &:hover {
                        background: rgba(var(--v-theme-error), 0.12);
                    }
                }
                &--develop-version {
                    font-size: 15px;
                    @include smartphone-horizontal {
                        font-size: 14.5px;
                    }
                }

                .navigation__link-icon {
                    margin-right: 14px;
                    @include smartphone-horizontal {
                        margin-right: 10px;
                    }
                }

                // アイコンのみモード: 正方形のアイコンボタンに変更
                &--icon-only {
                    width: 52px;
                    height: 52px;
                    padding-left: 0;
                    justify-content: center;
                    @include smartphone-horizontal {
                        width: 44px;
                        height: 44px;
                    }
                    @include smartphone-horizontal-short {
                        width: 40px;
                        height: 40px;
                    }

                    .navigation__link-icon {
                        margin-right: 0;
                    }
                }
            }
        }
    }
}

</style>