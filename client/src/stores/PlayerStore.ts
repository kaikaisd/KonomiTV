
import mitt from 'mitt';
import { defineStore } from 'pinia';

import type { IOfflineVideo } from '@/services/OfflineVideos';
import type PlayerController from '@/services/player/PlayerController';

import { ITweetCapture } from '@/components/Watch/Panel/Twitter.vue';
import { ICommentData } from '@/services/player/managers/LiveCommentManager';
import { IRecordedProgram, IRecordedProgramDefault } from '@/services/Videos';
import useSettingsStore from '@/stores/SettingsStore';


/**
 * プレイヤーに関連するイベントの型
 * PlayerManager 側からのイベントも UI 側からのイベントも PlayerEvents を通じて行う
 */
export type PlayerEvents = {
    // UI コンポーネントからプレイヤーに通知メッセージの送信を要求する
    // DPlayer.notice() の引数と同じで、そのまま DPlayer.notice() に渡される
    SendNotification: {
        message: string;  // 通知メッセージの内容
        duration?: number;  // 通知メッセージの表示時間 (ミリ秒)
        opacity?: number;  // 通知メッセージの透明度
        color?: string;  // 通知メッセージの文字色
    }
    // PlayerManager からプレイヤーの再起動が必要になったことを通知する
    PlayerRestartRequired: {
        message?: string;  // プレイヤーに通知するメッセージ
        message_delay_seconds?: number;  // メッセージを表示するまでの待機時間 (秒)
        is_error_message?: boolean;  // メッセージをエラーメッセージとして表示するか (既定は true)
        should_resume_quality?: boolean;  // 再起動後に直前の画質を引き継ぐかどうか (既定は true)
    };
    // PlayerController.setControlDisplayTimer() をそのまま呼び出す
    SetControlDisplayTimer: {
        event?: Event;  // マウスやタッチイベント (手動実行する際は省略する)
        is_player_region_event?: boolean;  // プレイヤー画面の中で発火したイベントなら true に設定する
        timeout_seconds?: number;  // 何も操作がない場合にコントロール UI を非表示にするまでの秒数
    }
    // CaptureManager からキャプチャの撮影が完了したことを通知する
    CaptureCompleted: {
        capture: Blob;  // キャプチャの Blob
        filename: string;  // キャプチャのファイル名 (UI からの手動ダウンロード時に使う)
    };
    // LiveCommentManager からコメントを受信したことを通知する
    CommentReceived: {
        is_initial_comments: boolean;  // 初期コメントかどうか
        comments: ICommentData[];  // コメントデータのリスト
    }
    // ライブ視聴: LiveCommentManager からコメントを送信したことを通知する
    CommentSendCompleted: {
        comment: ICommentData;  // 送信したコメントデータ (を整形したもの)
    }
    // 録画再生時: 再生位置が変更されたことを通知する
    PlaybackPositionChanged: {
        playback_position: number;  // 再生位置 (秒)
    }
    // 録画再生時: UI コンポーネントからプレイヤーに指定秒数へのシークを要求する
    SeekRequest: {
        playback_position: number;  // シーク先の再生位置 (秒)
    }
};


/**
 * ミニプレイヤーの状態を表す型
 * ミニプレイヤーがアクティブなとき、元の視聴画面の情報を保持する
 */
export interface IMiniPlayerState {
    // ミニプレイヤーの再生モード (Live: ライブ視聴, Video: ビデオ視聴)
    playback_mode: 'Live' | 'Video';
    // 最大化時に戻る元のルートパス (例: '/tv/watch/gr011', '/videos/watch/42')
    route_path: string;
    // ミニプレイヤーに表示する番組タイトル
    title: string;
    // ライブ視聴時のチャンネル ID (例: 'gr011')
    channel_id: string | null;
    // ビデオ視聴時の録画番組 ID
    video_id: number | null;
}


/**
 * PlayerController への参照をグローバルに保持するための変数
 * ミニプレイヤーモードでは Watch ページから離れても PlayerController を破棄せずに保持し続ける必要がある
 * Pinia ストアの state に入れるとリアクティブ化されて重くなるため、モジュールスコープのグローバル変数として保持する
 */
let active_player_controller: PlayerController | null = null;

/**
 * 現在アクティブな PlayerController を取得する
 * ミニプレイヤーモードで Watch ページを離れた後も PlayerController を参照するために使用する
 */
export function getActivePlayerController(): PlayerController | null {
    return active_player_controller;
}

/**
 * 現在アクティブな PlayerController を設定する
 * TV/Watch.vue や Videos/Watch.vue から呼び出され、PlayerController のライフサイクルを管理する
 */
export function setActivePlayerController(controller: PlayerController | null): void {
    active_player_controller = controller;
}


/**
 * プレイヤー側の再生系ロジックと UI 側で共有される状態を管理するストア
 * 主に PlayerController や PlayerManager から状態変化に合わせて変更された値をリアクティブに UI に反映するためのもの
 */
const usePlayerStore = defineStore('player', {
    state: () => ({

        // 現在視聴画面を表示しているか
        // 既定で表示していない
        is_watching: false,

        // PlayerController が初期化されているか
        is_player_initialized: false,

        // プレイヤーに関連するイベントを発行する EventEmitter
        event_emitter: mitt<PlayerEvents>(),

        // 現在視聴中の録画番組の情報
        // 視聴中の録画番組がない場合は IRecordedProgramDefault を設定すべき (初期値も IRecordedProgramDefault にしている)
        recorded_program: IRecordedProgramDefault as IRecordedProgram,

        // 仮想キーボードが表示されているか
        // 既定で表示されていない想定
        is_virtual_keyboard_display: false,

        // フルスクリーン状態かどうか
        is_fullscreen: false,

        // Document Picture-in-Picture モードかどうか
        is_document_pip: false,

        // コントロールを表示するか
        is_control_display: true,

        // パネルを表示するか
        // panel_display_state が "AlwaysDisplay" なら常に表示し、"AlwaysFold" なら常に折りたたむ
        // "RestorePreviousState" なら showed_panel_last_time の値を使い､前回の状態を復元する
        is_panel_display: (() => {
            const settings_store = useSettingsStore();
            switch (settings_store.settings.panel_display_state) {
                case 'AlwaysDisplay':
                    return true;
                case 'AlwaysFold':
                    return false;
                case 'RestorePreviousState':
                    return settings_store.settings.showed_panel_last_time;
            }
        })(),

        // ライブ視聴: 表示されるパネルのタブ
        tv_panel_active_tab: useSettingsStore().settings.tv_panel_active_tab,

        // ビデオ視聴: 表示されるパネルのタブ
        video_panel_active_tab: useSettingsStore().settings.video_panel_active_tab,

        // パネルの Twitter タブ内で表示されるタブ
        twitter_active_tab: useSettingsStore().settings.twitter_active_tab,

        // リモコンを表示するか
        is_remocon_display: false,

        // ザッピング（「前/次のチャンネル」ボタン or 上下キーショートカット）によるチャンネル移動かどうか
        is_zapping: false,

        // DPlayer の設定パネルが開いているか
        is_player_setting_panel_open: false,

        // 視聴画面内で手動選択された画質プロファイル
        // null の間は回線種別から選び、チャンネル切り替えなどでプレイヤーを作り直すときは手動選択を引き継ぐ
        selected_quality_profile_type: null as 'Wi-Fi' | 'Cellular' | null,

        // ビデオ視聴: CacheStorage に保存した単一画質を再生しているか
        is_offline_playback: false,

        // ビデオ視聴: 再生中の保存世代と画質
        offline_video: null as IOfflineVideo | null,

        // プレイヤーのローディング状態
        // 既定でローディングとする
        is_loading: true,

        // プレイヤーが映像の再生をバッファリングしているか
        // 視聴開始時以外にも、ネットワークが遅くて再生が一時的に途切れたときなどで表示される
        // 既定でバッファリング中とする
        is_video_buffering: true,

        // プレイヤーの再生が停止しているか
        // 既定で再生中とする
        is_video_paused: false,

        // プレイヤーの背景を表示するか
        // 既定で表示しない
        is_background_display: false,

        // プレイヤーの背景の URL
        background_url: '',

        // キーボードショートカットの一覧のモーダルを表示するか
        shortcut_key_modal: false,

        // L字画面のクロップ設定のモーダルを表示するか
        lshaped_screen_crop_settings_modal: false,

        // ライブ視聴: 現在のライブストリームのステータス
        // 既定で null (未視聴) とする
        live_stream_status: null as 'Offline' | 'Standby' | 'ONAir' | 'Idling' | 'Restart' | null,

        // ライブ視聴: ニコニコ実況への接続に失敗した際のエラーメッセージ
        // null のとき、エラーは発生していないとみなす
        live_comment_init_failed_message: null as string | null,

        // ビデオ視聴: 過去ログコメントへの取得に失敗した際のエラーメッセージ
        // null のとき、エラーは発生していないとみなす
        video_comment_init_failed_message: null as string | null,

        // Twitter パネルコンポーネントで利用する、ツイート添付候補のキャプチャのリスト
        // UI 上と KeyboardShortcutManager の両方から操作する必要があるため PlayerStore に持たせている
        twitter_captures: [] as ITweetCapture[],

        // Twitter パネルコンポーネントで利用する、ツイートに添付するキャプチャの Blob データのリスト
        // Twitter パネル本体とキャプチャタブの間で共有するため PlayerStore に持たせている
        twitter_selected_capture_blobs: [] as Blob[],

        // Twitter パネルコンポーネントで利用する、キャプチャを拡大表示するモーダルの表示状態
        // UI 上と KeyboardShortcutManager の両方から操作する必要があるため PlayerStore に持たせている
        twitter_zoom_capture_modal: false,

        // Twitter パネルコンポーネントで利用する、現在モーダルで拡大表示中のキャプチャ
        // UI 上と KeyboardShortcutManager の両方から操作する必要があるため PlayerStore に持たせている
        twitter_zoom_capture: null as ITweetCapture | null,

        // ミニプレイヤーが表示中かどうか
        // YouTube のように、視聴画面から他のページに遷移しても小さなプレイヤーを画面右下に表示し続ける機能
        is_mini_player: false,

        // ミニプレイヤーの状態情報
        // ミニプレイヤーがアクティブなときの再生モード・ルート・タイトルなどの情報を保持する
        mini_player_state: null as IMiniPlayerState | null,
    }),
    actions: {

        /**
         * 視聴画面を開き、再生処理を開始する際に必ず呼び出さなければならない
         * 呼び出すと自動的に状態がリセットされ、is_watching が true になる
         */
        startWatching(): void {
            this.reset();
            this.is_watching = true;
        },

        /**
         * 視聴画面を閉じ、再生処理を終了する際に必ず呼び出さなければならない
         * 呼び出すと自動的に状態がリセットされ、is_watching が false になる
         */
        stopWatching(): void {
            this.reset();
            this.is_watching = false;
        },

        /**
         * PlayerStore の内容を初期値に戻す
         * startWatching() / stopWatching() で呼び出される
         */
        reset(): void {
            this.is_watching = false;
            this.is_player_initialized = false;
            this.recorded_program = IRecordedProgramDefault;
            this.is_virtual_keyboard_display = false;
            this.is_fullscreen = false;
            this.is_document_pip = false;
            this.is_control_display = true;
            this.is_panel_display = (() => {
                const settings_store = useSettingsStore();
                switch (settings_store.settings.panel_display_state) {
                    case 'AlwaysDisplay':
                        return true;
                    case 'AlwaysFold':
                        return false;
                    case 'RestorePreviousState':
                        return settings_store.settings.showed_panel_last_time;
                }
            })();
            this.tv_panel_active_tab = useSettingsStore().settings.tv_panel_active_tab;
            this.video_panel_active_tab = useSettingsStore().settings.video_panel_active_tab;
            this.twitter_active_tab = useSettingsStore().settings.twitter_active_tab;
            this.is_remocon_display = false;
            this.is_zapping = false;
            this.is_player_setting_panel_open = false;
            this.selected_quality_profile_type = null;
            this.is_offline_playback = false;
            this.offline_video = null;
            this.is_loading = true;
            this.is_video_buffering = true;
            this.is_video_paused = false;
            this.is_background_display = false;
            this.background_url = '';
            this.shortcut_key_modal = false;
            this.live_stream_status = null;
            this.live_comment_init_failed_message = null;
            this.twitter_captures = [];
            this.twitter_zoom_capture_modal = false;
            this.twitter_zoom_capture = null;
            // ミニプレイヤー関連の状態はリセットしない (ページ遷移をまたいで維持するため)
        },

        /**
         * ミニプレイヤーモードに移行する
         * DPlayer の DOM 要素を App.vue の永続コンテナに移動し、視聴画面から離れても再生を継続する
         * @param state ミニプレイヤーの状態情報 (再生モード・ルートパス・タイトルなど)
         */
        minimizePlayer(state: IMiniPlayerState): void {
            // BML ブラウザ (データ放送) のコンテナを非表示にしてから DOM を移動する
            // BML ブラウザ内部の ResizeObserver が DOM 移動中に 0 サイズの canvas に対して
            // drawImage() を実行してしまう問題 (InvalidStateError) を回避するため
            const bml_browser_container = document.querySelector<HTMLDivElement>('.dplayer-bml-browser');
            if (bml_browser_container) {
                bml_browser_container.style.display = 'none';
            }

            // DPlayer の DOM 要素をミニプレイヤーコンテナに移動する
            // display: none にすると <video> のデコーダが停止し映像が黒くなるため、
            // 代わりに画面外に配置して非表示にしつつデコードを継続させる
            const dplayer_element = document.querySelector<HTMLDivElement>('.watch-player__dplayer');
            const mini_player_container = document.getElementById('mini-player-persistent-container');
            if (dplayer_element && mini_player_container) {
                mini_player_container.style.display = 'block';
                mini_player_container.style.position = 'fixed';
                mini_player_container.style.top = '-9999px';
                mini_player_container.style.width = '1px';
                mini_player_container.style.height = '1px';
                mini_player_container.style.overflow = 'hidden';
                mini_player_container.appendChild(dplayer_element);
            }

            // ミニプレイヤーの状態を設定
            this.is_mini_player = true;
            this.mini_player_state = state;

            console.log(`[PlayerStore] Mini player activated. (mode: ${state.playback_mode}, route: ${state.route_path})`);
        },

        /**
         * ミニプレイヤーモードを終了してフルスクリーンの視聴画面に戻る
         * DPlayer の DOM 要素を Watch コンポーネントのプレイヤーコンテナに移動する
         */
        restoreFromMiniPlayer(): void {
            // DPlayer の DOM 要素を視聴画面のプレイヤーコンテナに戻す
            const mini_player_container = document.getElementById('mini-player-persistent-container');
            const watch_player_container = document.querySelector<HTMLDivElement>('.watch-player');
            if (mini_player_container && watch_player_container) {
                const dplayer_element = mini_player_container.querySelector<HTMLDivElement>('.watch-player__dplayer');
                if (dplayer_element) {
                    // Player.vue の空の .watch-player__dplayer を置き換える
                    const placeholder = watch_player_container.querySelector<HTMLDivElement>('.watch-player__dplayer');
                    if (placeholder) {
                        watch_player_container.replaceChild(dplayer_element, placeholder);
                    }
                }
                // minimizePlayer() で設定した画面外配置のスタイルをリセットする
                mini_player_container.style.display = 'none';
                mini_player_container.style.position = '';
                mini_player_container.style.top = '';
                mini_player_container.style.width = '';
                mini_player_container.style.height = '';
                mini_player_container.style.overflow = '';
            }

            // BML ブラウザのコンテナを再表示する (minimizePlayer() で非表示にしたものを元に戻す)
            const bml_browser_container = document.querySelector<HTMLDivElement>('.dplayer-bml-browser');
            if (bml_browser_container) {
                bml_browser_container.style.display = '';
            }

            // ミニプレイヤーの状態をリセット
            this.is_mini_player = false;
            this.mini_player_state = null;

            console.log('[PlayerStore] Mini player deactivated, restored to full player.');
        },

        /**
         * ミニプレイヤーを完全に閉じて再生を停止する
         * PlayerController を破棄し、すべてのミニプレイヤー関連状態をリセットする
         */
        async closeMiniPlayer(): Promise<void> {
            const controller = getActivePlayerController();
            if (controller) {
                await controller.destroy();
                setActivePlayerController(null);
            }

            // ミニプレイヤーコンテナ内の DPlayer DOM を削除し、スタイルをリセットする
            const mini_player_container = document.getElementById('mini-player-persistent-container');
            if (mini_player_container) {
                mini_player_container.innerHTML = '';
                mini_player_container.style.display = 'none';
                mini_player_container.style.position = '';
                mini_player_container.style.top = '';
                mini_player_container.style.width = '';
                mini_player_container.style.height = '';
                mini_player_container.style.overflow = '';
            }

            // 状態をリセット
            this.is_mini_player = false;
            this.mini_player_state = null;
            this.is_watching = false;
            this.is_player_initialized = false;

            console.log('[PlayerStore] Mini player closed and destroyed.');
        },
    }
});

export default usePlayerStore;
