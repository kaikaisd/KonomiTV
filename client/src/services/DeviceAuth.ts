
import APIClient from '@/services/APIClient';


/**
 * 端末ペアリング (OAuth 2.0 Device Authorization Grant 相当) 関連の API 操作を提供する
 * テレビ向けクライアントなど、文字入力が困難な端末を KonomiTV アカウントへ紐付けるために利用する
 */
export default class DeviceAuth {

    /**
     * 端末側に表示されているユーザーコードを承認し、その端末をログイン中のアカウントへ紐付ける
     * @param user_code 端末側に表示されている8文字のユーザーコード
     * @returns 承認に成功したら true 、失敗したら false
     */
    static async approve(user_code: string): Promise<boolean> {
        const response = await APIClient.post('/users/device-auth/approve', { user_code });
        return response.type !== 'error';
    }
}
