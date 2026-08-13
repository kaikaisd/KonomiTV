import unittest

from app.WatchedHistory import MergeWatchedHistory


def history(video_id: int, position: float, created_at: float, updated_at: float) -> dict[str, int | float]:
    """
    テスト用の視聴履歴 1 件分の辞書を組み立てる。

    Args:
        video_id (int): 録画番組 ID 。
        position (float): 最終再生位置 (秒) 。
        created_at (float): 視聴を開始した時刻の UNIX タイムスタンプ。
        updated_at (float): 最終更新時刻の UNIX タイムスタンプ。

    Returns:
        dict[str, int | float]: 視聴履歴 1 件分の辞書。
    """

    return {
        'video_id': video_id,
        'last_playback_position': position,
        'created_at': created_at,
        'updated_at': updated_at,
    }


class WatchedHistoryMergeTest(unittest.TestCase):
    """MergeWatchedHistory() が複数端末の視聴履歴を正しくマージすることを検証する。"""

    def test_merge_watched_history_keeps_latest_per_video(self) -> None:
        """録画番組ごとに最終更新時刻が新しい履歴が残り、視聴開始時刻は最も古い値が引き継がれることを検証する。"""

        merged = MergeWatchedHistory(
            [history(1, 30, 10, 30), history(2, 20, 20, 20)],
            [history(1, 15, 15, 15), history(2, 40, 25, 40), history(3, 50, 50, 50)],
            50,
        )

        # video_id 1 は受信側の方が古いため巻き戻らず、video_id 2 は受信側が新しいため更新される
        self.assertEqual(
            [(item['video_id'], item['last_playback_position']) for item in merged],
            [(3, 50), (2, 40), (1, 30)],
        )
        # video_id 2 の created_at は、サーバー側が持っていたより古い値が維持される
        self.assertEqual(merged[1]['created_at'], 20)

    def test_merge_watched_history_limits_oldest_updates(self) -> None:
        """保存上限を超えた場合に、最終更新時刻が古い履歴から破棄されることを検証する。"""

        merged = MergeWatchedHistory([], [history(i, i, i + 1, i + 1) for i in range(4)], 2)
        self.assertEqual([item['video_id'] for item in merged], [3, 2])


if __name__ == '__main__':
    unittest.main()
