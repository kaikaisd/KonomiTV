import asyncio
import pathlib
import tempfile
import unittest
from unittest import mock

import anyio

from app.metadata.CMAnalyzer import (
    CMAnalyzerRequest,
    GenericCMAnalyzer,
)
from app.metadata.CMSectionsDetector import CMSectionsDetector


class CMAnalyzerRuntimeTest(unittest.TestCase):
    """専用ランタイムが未導入の環境で GenericCMAnalyzer が安全に降格することを検証する。"""

    def test_analyze_reports_unavailable_without_runtime(self) -> None:
        """ランタイムが存在しない場合、例外ではなく unsupported を返す。"""

        # 実在しないランタイムディレクトリを指定し、未導入環境を再現する
        analyzer = GenericCMAnalyzer(runtime_directory=pathlib.Path('/nonexistent/CMAnalysis'))
        with tempfile.TemporaryDirectory() as work_directory:
            result = asyncio.run(analyzer.analyze(CMAnalyzerRequest(
                recorded_file_path = pathlib.Path('/nonexistent/recorded.ts'),
                work_directory = pathlib.Path(work_directory),
                service_id = None,
                hardware_device = None,
                duration_seconds = 1800.0,
                container_format = 'MPEG-TS',
            )))

        # ランタイム不足は解析失敗ではなく「解析器が利用不可」として報告される
        self.assertEqual(result.status, 'unsupported')
        self.assertEqual(result.error_code, 'AnalyzerUnavailable')
        self.assertEqual(result.sections, ())


class CMSectionsDetectorFallbackTest(unittest.IsolatedAsyncioTestCase):
    """JLS が使えない環境で silencedetect へフォールバックすることを検証する。"""

    def setUp(self) -> None:
        self.detector = CMSectionsDetector(
            file_path = anyio.Path('/nonexistent/recorded.ts'),
            duration_sec = 1800.0,
            container_format = 'MPEG-TS',
            service_id = 1024,
        )

    async def test_falls_back_to_silencedetect_when_jls_unavailable(self) -> None:
        """JLS が None を返したとき、silencedetect の結果が採用される。"""

        silencedetect_sections = [{'start_time': 60.0, 'end_time': 90.0}]
        with (
            mock.patch.object(
                CMSectionsDetector, '_CMSectionsDetector__detectFromChapterFile',
                new = mock.AsyncMock(return_value=None),
            ),
            mock.patch.object(
                CMSectionsDetector, '_CMSectionsDetector__detectWithJLS',
                new = mock.AsyncMock(return_value=None),
            ) as detect_with_jls,
            mock.patch.object(
                CMSectionsDetector, '_CMSectionsDetector__detectWithFFmpeg',
                new = mock.AsyncMock(return_value=silencedetect_sections),
            ) as detect_with_ffmpeg,
            mock.patch('app.metadata.CMSectionsDetector.RecordedVideo') as recorded_video,
        ):
            recorded_video.get_or_none = mock.AsyncMock(return_value=None)
            await self.detector.detectAndSave()

        # JLS を試した上で、silencedetect へフォールバックしていることを確認する
        detect_with_jls.assert_awaited_once()
        detect_with_ffmpeg.assert_awaited_once()

    async def test_does_not_run_silencedetect_when_jls_succeeds(self) -> None:
        """JLS が CM 区間を返したとき、silencedetect は実行されない。"""

        jls_sections = [{'start_time': 120.0, 'end_time': 150.0}]
        with (
            mock.patch.object(
                CMSectionsDetector, '_CMSectionsDetector__detectFromChapterFile',
                new = mock.AsyncMock(return_value=None),
            ),
            mock.patch.object(
                CMSectionsDetector, '_CMSectionsDetector__detectWithJLS',
                new = mock.AsyncMock(return_value=jls_sections),
            ),
            mock.patch.object(
                CMSectionsDetector, '_CMSectionsDetector__detectWithFFmpeg',
                new = mock.AsyncMock(return_value=None),
            ) as detect_with_ffmpeg,
            mock.patch('app.metadata.CMSectionsDetector.RecordedVideo') as recorded_video,
        ):
            recorded_video.get_or_none = mock.AsyncMock(return_value=None)
            await self.detector.detectAndSave()

        # JLS で検出できた場合、計算コストの高い silencedetect は実行しない
        detect_with_ffmpeg.assert_not_awaited()

    async def test_chapter_file_takes_precedence_over_analysis(self) -> None:
        """チャプターファイルがある場合、JLS も silencedetect も実行されない。"""

        chapter_sections = [{'start_time': 30.0, 'end_time': 60.0}]
        with (
            mock.patch.object(
                CMSectionsDetector, '_CMSectionsDetector__detectFromChapterFile',
                new = mock.AsyncMock(return_value=chapter_sections),
            ),
            mock.patch.object(
                CMSectionsDetector, '_CMSectionsDetector__detectWithJLS',
                new = mock.AsyncMock(return_value=None),
            ) as detect_with_jls,
            mock.patch.object(
                CMSectionsDetector, '_CMSectionsDetector__detectWithFFmpeg',
                new = mock.AsyncMock(return_value=None),
            ) as detect_with_ffmpeg,
            mock.patch('app.metadata.CMSectionsDetector.RecordedVideo') as recorded_video,
        ):
            recorded_video.get_or_none = mock.AsyncMock(return_value=None)
            await self.detector.detectAndSave()

        detect_with_jls.assert_not_awaited()
        detect_with_ffmpeg.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
