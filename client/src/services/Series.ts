
import APIClient from '@/services/APIClient';
import { IChannel } from '@/services/Channels';
import { IRecordedProgram } from '@/services/Videos';


/** シリーズ情報を表すインターフェース */
export interface ISeries {
    id: number;
    title: string;
    description: string;
    genres: { major: string; middle: string; }[];
    bangumi_subject_id: number | null;
    bangumi_subject_name: string | null;
    bangumi_subject_name_cn: string | null;
    bangumi_subject_summary: string | null;
    bangumi_subject_image_url: string | null;
    broadcast_periods: ISeriesBroadcastPeriod[];
    created_at: string;
    updated_at: string;
}

/** シリーズ情報リストを表すインターフェース */
export interface ISeriesList {
    total: number;
    series_list: ISeries[];
}

/** 放送中シリーズを表すインターフェース */
export interface IOnAirSeries {
    id: number;
    title: string;
    thumbnail_recorded_program_ids: number[];
    channel_ids: string[];
    recorded_episodes_count: number;
    missing_episodes_count: number;
    partially_recorded_episodes_count: number;
    weekday: number;
    broadcast_time: string;
    latest_broadcast_at: string;
}

/** 放送中シリーズリストを表すインターフェース */
export interface IOnAirSeriesList {
    series_list: IOnAirSeries[];
}

/** シリーズ一覧に表示する概要情報を表すインターフェース */
export interface ISeriesSummary {
    id: number;
    title: string;
    description: string;
    genres: { major: string; middle: string; }[];
    thumbnail_recorded_program_ids: number[];
    channel_ids: string[];
    official_website_url: string | null;
    bangumi_subject_id: number | null;
    bangumi_subject_name: string | null;
    bangumi_subject_name_cn: string | null;
    bangumi_subject_summary: string | null;
    bangumi_subject_image_url: string | null;
    recorded_programs_count: number;
    created_at: string;
    updated_at: string;
}

/** シリーズ放送期間を表すインターフェース */
export interface ISeriesBroadcastPeriod {
    channel: IChannel;
    start_date: string;
    end_date: string;
    recorded_programs: IRecordedProgram[];
}


class Series {

    /**
     * シリーズ一覧を取得する
     * @param order ソート順序 ('desc' or 'asc')
     * @param page ページ番号
     * @returns シリーズ一覧情報 or シリーズ一覧情報の取得に失敗した場合は null
     */
    /**
     * 放送中シリーズ一覧を取得する
     * @returns 放送中シリーズ一覧 or 取得に失敗した場合は null
     */
    static async fetchOnAirSeriesList(): Promise<IOnAirSeriesList | null> {

        const response = await APIClient.get<IOnAirSeriesList>('/series/on-air');
        if (response.type === 'error') {
            APIClient.showGenericError(response, '放送中のシリーズを取得できませんでした。');
            return null;
        }
        return response.data;
    }


    /**
     * シリーズ概要を取得する
     * @param series_id シリーズ ID
     * @returns シリーズ概要 or 取得に失敗した場合は null
     */
    static async fetchSeriesSummary(series_id: number): Promise<ISeriesSummary | null> {

        const response = await APIClient.get<ISeriesSummary>(`/series/${series_id}/summary`);
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズ概要を取得できませんでした。');
            return null;
        }
        return response.data;
    }


    static async fetchSeriesList(order: 'desc' | 'asc' = 'desc', page: number = 1): Promise<ISeriesList | null> {

        // API リクエストを実行
        const response = await APIClient.get<ISeriesList>('/series', {
            params: {
                order,
                page,
            },
        });

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズ一覧を取得できませんでした。');
            return null;
        }

        return response.data;
    }


    /**
     * シリーズ番組を検索する
     * @param query 検索キーワード
     * @param order ソート順序 ('desc' or 'asc')
     * @param page ページ番号
     * @returns 検索結果のシリーズ番組一覧情報 or 検索に失敗した場合は null
     */
    static async searchSeries(query: string, order: 'desc' | 'asc' = 'desc', page: number = 1): Promise<ISeriesList | null> {

        // API リクエストを実行
        const response = await APIClient.get<ISeriesList>('/series/search', {
            params: {
                query,
                order,
                page,
            },
        });

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズ番組の検索に失敗しました。');
            return null;
        }

        return response.data;
    }


    /**
     * シリーズ情報を取得する
     * @param series_id シリーズ ID
     * @returns シリーズ情報 or シリーズ情報の取得に失敗した場合は null
     */
    static async fetchSeries(series_id: number): Promise<ISeries | null> {

        // API リクエストを実行
        const response = await APIClient.get<ISeries>(`/series/${series_id}`);

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズ情報を取得できませんでした。');
            return null;
        }

        return response.data;
    }


    /**
     * シリーズ名を変更する
     * @param series_id シリーズ ID
     * @param title 変更後のシリーズタイトル
     * @returns 更新後のシリーズ情報 or 変更に失敗した場合は null
     */
    static async updateSeries(series_id: number, title: string): Promise<ISeries | null> {

        // API リクエストを実行
        const response = await APIClient.put<ISeries>(`/series/${series_id}`, { title });

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズ名の変更に失敗しました。');
            return null;
        }

        return response.data;
    }


    /**
     * シリーズから録画番組を除外する
     * @param series_id シリーズ ID
     * @param program_id 除外する録画番組の ID
     * @returns 除外に成功した場合は true、失敗した場合は false
     */
    static async removeProgramFromSeries(series_id: number, program_id: number): Promise<boolean> {

        // API リクエストを実行
        const response = await APIClient.delete(`/series/${series_id}/programs/${program_id}`);

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズからの除外に失敗しました。');
            return false;
        }

        return true;
    }


    /**
     * 新しいシリーズを作成する
     * @param title シリーズのタイトル
     * @returns 作成されたシリーズ情報 or 作成に失敗した場合は null
     */
    static async createSeries(title: string): Promise<ISeries | null> {

        // API リクエストを実行
        const response = await APIClient.post<ISeries>('/series', { title });

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズの作成に失敗しました。');
            return null;
        }

        return response.data;
    }


    /**
     * シリーズを削除する
     * @param series_id シリーズ ID
     * @returns 削除に成功した場合は true、失敗した場合は false
     */
    static async deleteSeries(series_id: number): Promise<boolean> {

        // API リクエストを実行
        const response = await APIClient.delete(`/series/${series_id}`);

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズの削除に失敗しました。');
            return false;
        }

        return true;
    }


    /**
     * シリーズに録画番組を追加する
     * @param series_id シリーズ ID
     * @param program_id 追加する録画番組の ID
     * @returns 更新後のシリーズ情報 or 追加に失敗した場合は null
     */
    static async addProgramToSeries(series_id: number, program_id: number): Promise<ISeries | null> {

        // API リクエストを実行
        const response = await APIClient.post<ISeries>(`/series/${series_id}/programs/${program_id}`);

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズへの追加に失敗しました。');
            return null;
        }

        return response.data;
    }


    /**
     * シリーズをマージする (マージ元の全番組をマージ先に移動)
     * @param source_id マージ元シリーズ ID
     * @param target_id マージ先シリーズ ID
     * @returns マージ後のターゲットシリーズ情報 or マージに失敗した場合は null
     */
    static async mergeSeries(source_id: number, target_id: number): Promise<ISeries | null> {

        // API リクエストを実行
        const response = await APIClient.post<ISeries>(`/series/${source_id}/merge/${target_id}`);

        // エラー処理
        if (response.type === 'error') {
            APIClient.showGenericError(response, 'シリーズのマージに失敗しました。');
            return null;
        }

        return response.data;
    }
}

export default Series;
