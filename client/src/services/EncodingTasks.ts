
import APIClient from '@/services/APIClient';


/**
 * エンコーダーの種別
 */
export type EncoderType = 'FFmpeg' | 'QSVEncC' | 'NVEncC' | 'VCEEncC' | 'rkmppenc';

/**
 * エンコードタスクのステータス
 */
export type EncodingTaskStatusType = 'Pending' | 'Encoding' | 'Completed' | 'Failed' | 'Cancelled';

/**
 * エンコードタスクの情報
 */
export interface IEncodingTask {
    id: number;
    source_file_path: string;
    output_file_path: string;
    recorded_video_id: number | null;
    encoder_type: EncoderType;
    video_codec: 'H.264' | 'H.265';
    quality_preset: string;
    video_bitrate: string;
    audio_bitrate: string;
    cm_removal: boolean;
    status: EncodingTaskStatusType;
    priority: number;
    progress: number;
    fail_reason: string;
    added_at: string;
    encoding_started_at: string | null;
    encoding_finished_at: string | null;
}

/**
 * エンコードタスク一覧 API のレスポンス
 */
export interface IEncodingTaskList {
    total: number;
    encoding_tasks: IEncodingTask[];
}

/**
 * エンコードタスク追加リクエスト
 */
export interface IEncodingTaskAddRequest {
    recorded_video_id: number;
    encoder_type?: EncoderType;
    video_codec?: 'H.264' | 'H.265';
    quality_preset?: string;
    video_bitrate?: string;
    audio_bitrate?: string;
    cm_removal?: boolean;
    priority?: number;
}

/**
 * エンコードタスク更新リクエスト
 */
export interface IEncodingTaskUpdateRequest {
    priority?: number;
    status?: 'Cancelled';
}


class EncodingTasks {

    /**
     * エンコードタスクの一覧を取得する
     * @param status ステータスでフィルタ (省略時は全件取得)
     * @param page ページ番号
     * @param per_page 1ページあたりの件数
     * @returns エンコードタスク一覧、取得失敗時は null
     */
    static async fetchAll(status?: EncodingTaskStatusType, page: number = 1, per_page: number = 50): Promise<IEncodingTaskList | null> {
        const params: Record<string, string | number> = { page, per_page };
        if (status) {
            params.status = status;
        }
        const response = await APIClient.get<IEncodingTaskList>('/encoding-tasks', { params });

        if (response.type === 'error') {
            APIClient.showGenericError(response, 'エンコードタスク一覧を取得できませんでした。');
            return null;
        }

        return response.data;
    }

    /**
     * 新しいエンコードタスクをキューに追加する
     * @param request エンコードタスク追加リクエスト
     * @returns 追加されたエンコードタスク、失敗時は null
     */
    static async add(request: IEncodingTaskAddRequest): Promise<IEncodingTask | null> {
        const response = await APIClient.post<IEncodingTask>('/encoding-tasks', request);

        if (response.type === 'error') {
            APIClient.showGenericError(response, 'エンコードタスクの追加に失敗しました。');
            return null;
        }

        return response.data;
    }

    /**
     * エンコードタスクを更新する (優先度変更・キャンセル)
     * @param task_id タスク ID
     * @param request 更新リクエスト
     * @returns 更新されたエンコードタスク、失敗時は null
     */
    static async update(task_id: number, request: IEncodingTaskUpdateRequest): Promise<IEncodingTask | null> {
        const response = await APIClient.put<IEncodingTask>(`/encoding-tasks/${task_id}`, request);

        if (response.type === 'error') {
            APIClient.showGenericError(response, 'エンコードタスクの更新に失敗しました。');
            return null;
        }

        return response.data;
    }

    /**
     * エンコードタスクを削除する
     * @param task_id タスク ID
     * @returns 削除に成功した場合は true
     */
    static async delete(task_id: number): Promise<boolean> {
        const response = await APIClient.delete(`/encoding-tasks/${task_id}`);

        if (response.type === 'error') {
            APIClient.showGenericError(response, 'エンコードタスクの削除に失敗しました。');
            return false;
        }

        return true;
    }

    /**
     * 失敗またはキャンセル済みのエンコードタスクをリトライする
     * @param task_id タスク ID
     * @returns リトライされたエンコードタスク、失敗時は null
     */
    static async retry(task_id: number): Promise<IEncodingTask | null> {
        const response = await APIClient.post<IEncodingTask>(`/encoding-tasks/${task_id}/retry`);

        if (response.type === 'error') {
            APIClient.showGenericError(response, 'エンコードタスクのリトライに失敗しました。');
            return null;
        }

        return response.data;
    }
}

export default EncodingTasks;
