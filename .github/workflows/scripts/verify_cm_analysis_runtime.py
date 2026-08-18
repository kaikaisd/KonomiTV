#!/usr/bin/env python3
"""
ビルド済みの CM 解析ランタイム (thirdparty/CMAnalysis) が実際に動作するかを検証する。

build-cm-analysis.sh が成功しても、動的リンクや rpath の設定が誤っていれば
実行時に初めて失敗する。このスクリプトは合成した検証用クリップに対して
GenericCMAnalyzer を実際に走らせ、chapter_exe / logoframe / join_logo_scp /
ffmsindex が起動して解析が完走することまでを確認する。

Usage:
    poetry run python verify_cm_analysis_runtime.py <runtime_directory>
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import subprocess
import sys
import tempfile
from pathlib import Path


# app パッケージを import できるよう、リポジトリ内の server ディレクトリを sys.path へ追加する
## 本スクリプトは .github/workflows/scripts/ に置かれているため、リポジトリルートは 3 階層上になる
SERVER_DIRECTORY = Path(__file__).resolve().parents[3] / 'server'
if str(SERVER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SERVER_DIRECTORY))


# 検証用クリップの長さ (秒)
## chapter_exe が無音・シーンチェンジ境界を検出できる程度の長さがあればよい
CLIP_DURATION_SECONDS = 60
# 本編とみなす区間 (この区間にだけロゴを描画する)
PROGRAM_RANGES = ((0, 20), (40, 60))
# 合成素材では成立しないため、検証の失敗とはみなさないエラーコード
## いずれもネイティブバイナリは正常に起動・終了しており、
## 「本編と CM の区間を確定できなかった」という素材側の性質を表す。
## 実素材でしか評価できない検出精度をここで判定しないための区別
CONTENT_DEPENDENT_ERROR_CODES = frozenset({
    # join_logo_scp が本編範囲 (Trim) を一意に決められなかった
    'AnalyzerOutputInvalid',
    # chapter_exe の出力からチャプター候補を解釈できなかった
    'ChapterOutputInvalid',
})


def BuildVerificationClip(ffmpeg_path: Path, output_path: Path) -> None:
    """
    検証用の MPEG-TS クリップを合成する。

    本編区間にだけロゴ相当の矩形を描画し、区間の境目に無音を挟むことで、
    chapter_exe と logoframe の双方が処理すべき素材を含んだクリップを作る。

    Args:
        ffmpeg_path (Path): 利用する FFmpeg のパス。
        output_path (Path): 出力する MPEG-TS ファイルのパス。

    Raises:
        subprocess.CalledProcessError: FFmpeg の実行に失敗した場合。
    """

    # 本編区間だけロゴを描画する enable 式を組み立てる
    logo_enable = '+'.join(f'between(t,{start},{end})' for start, end in PROGRAM_RANGES)
    # 本編区間だけ音声を鳴らし、CM 区間との境目を無音にする
    audio_enable = '+'.join(f'between(t,{start},{end})' for start, end in PROGRAM_RANGES)

    # generate-cm-smoke-fixture.py が作るロゴと同じ形状 (白い矩形の中に黒い芯) を描画する
    video_filter = (
        f'drawbox=x=16:y=16:w=32:h=16:color=white@1.0:t=fill:enable=\'{logo_enable}\','
        f'drawbox=x=20:y=20:w=24:h=8:color=black@1.0:t=fill:enable=\'{logo_enable}\''
    )

    subprocess.run(
        [
            str(ffmpeg_path), '-y', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=30000/1001:duration={CLIP_DURATION_SECONDS}',
            '-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate=48000:duration={CLIP_DURATION_SECONDS}',
            # 入力が 2 つあるため、どのストリームを使うかを明示する
            '-map', '0:v:0', '-map', '1:a:0',
            '-vf', video_filter,
            '-af', f'volume=0:enable=\'not({audio_enable})\'',
            '-t', str(CLIP_DURATION_SECONDS),
            '-c:v', 'mpeg2video', '-b:v', '4M', '-g', '15',
            '-c:a', 'mp2', '-b:a', '256k', '-ac', '2',
            '-f', 'mpegts', str(output_path),
        ],
        check = True,
    )


def GenerateSmokeLogo(fixture_script: Path, output_path: Path) -> None:
    """
    logoframe に渡す検証用ロゴファイルを生成する。

    Args:
        fixture_script (Path): generate-cm-smoke-fixture.py のパス。
        output_path (Path): 出力するロゴファイルのパス。

    Raises:
        subprocess.CalledProcessError: 生成スクリプトの実行に失敗した場合。
    """

    subprocess.run([sys.executable, str(fixture_script), str(output_path)], check=True)


async def Verify(runtime_directory: Path, ffmpeg_path: Path, ffprobe_path: Path, fixture_script: Path) -> int:
    """
    検証用クリップに対して CM 解析を実行し、完走したかどうかを判定する。

    Args:
        runtime_directory (Path): ビルド済みの CMAnalysis ランタイムのディレクトリ。
        ffmpeg_path (Path): 利用する FFmpeg のパス。
        ffprobe_path (Path): 利用する FFprobe のパス。
        fixture_script (Path): generate-cm-smoke-fixture.py のパス。

    Returns:
        int: 検証に成功した場合は 0、失敗した場合は 1。
    """

    from app.metadata.CMAnalyzer import CMAnalyzerRequest, GenericCMAnalyzer

    analyzer = GenericCMAnalyzer(
        runtime_directory = runtime_directory,
        ffmpeg_path = ffmpeg_path,
        ffprobe_path = ffprobe_path,
    )

    # GenericCMAnalyzer が必須とするファイルが揃っているかを、解析器自身の定義に従って確認する
    ## build-cm-analysis.sh 側の存在確認とは対象が異なり、例えば libffms2.so
    ## (バージョン番号なしのシンボリックリンク) はこちらでしか確認されない
    required_paths = {
        'libffms2.so': analyzer.ffms2_path,
        'ffmsindex': analyzer.ffmsindex_path,
        'chapter_exe': analyzer.chapter_executable_path,
        'logoframe': analyzer.logoframe_path,
        'join_logo_scp': analyzer.join_logo_scp_path,
        'JL_標準.txt': analyzer.join_logo_scp_command_path,
        'Runtime-Manifest.json': analyzer.runtime_manifest_path,
    }
    print('--- GenericCMAnalyzer が要求するファイルの存在確認 ---', flush=True)
    missing = False
    for name, path in required_paths.items():
        if path.is_file():
            print(f'  OK   {name}: {path}', flush=True)
        else:
            print(f'  NG   {name}: {path} が存在しません', flush=True)
            missing = True
    if missing is True:
        print('CM 解析ランタイムに不足があります。', flush=True)
        return 1

    with tempfile.TemporaryDirectory() as temporary_directory:
        work_directory = Path(temporary_directory)
        clip_path = work_directory / 'verification-clip.ts'
        logo_path = work_directory / 'verification-logo.lgd'
        analysis_directory = work_directory / 'analysis'
        analysis_directory.mkdir()

        print('--- 検証用クリップとロゴを生成 ---', flush=True)
        BuildVerificationClip(ffmpeg_path, clip_path)
        GenerateSmokeLogo(fixture_script, logo_path)
        print(f'  クリップ: {clip_path.stat().st_size} bytes', flush=True)
        print(f'  ロゴ:     {logo_path.stat().st_size} bytes', flush=True)

        print('--- CM 解析を実行 ---', flush=True)
        result = await analyzer.analyze(CMAnalyzerRequest(
            recorded_file_path = clip_path,
            work_directory = analysis_directory,
            # ロゴを渡すことで logoframe も実際に起動させる
            ## ロゴが一致しなくても警告になるだけで失敗にはならないため、
            ## ここでは logoframe が起動してクラッシュしないことの確認が目的
            logo_paths = (logo_path,),
            duration_seconds = float(CLIP_DURATION_SECONDS),
            container_format = 'MPEG-TS',
        ))

        # 失敗時の原因を追えるよう、結果は必ず全項目を出力する
        print('--- 解析結果 ---', flush=True)
        for field in dataclasses.fields(result):
            value = getattr(result, field.name)
            if field.name == 'sections':
                print(f'  sections: {len(value)} 件', flush=True)
                for section in value:
                    print(f'    {section["start_time"]:.2f} - {section["end_time"]:.2f}', flush=True)
            else:
                print(f'  {field.name}: {value}', flush=True)

        # 各ネイティブバイナリが実際に起動したことを、解析結果から個別に確認する
        ## 単に status を見るだけでは、素材の性質による不成立と
        ## バイナリが起動できない致命的な不具合とを区別できない
        print('--- 各段階の実行確認 ---', flush=True)
        stage_evidence = {
            # descriptor が埋まっていれば FFprobe による入力解決まで到達している
            'FFprobe (入力ストリーム解決)': result.descriptor is not None,
            # フレーム数が得られていれば FFMS2 の索引作成と chapter_exe の実行まで到達している
            'FFMS2 / chapter_exe (索引とチャプター抽出)': (result.total_frames or 0) > 0,
            # ロゴ一致・不一致のいずれかが記録されていれば logoframe は起動して正常終了している
            'logoframe (ロゴ走査)': (
                result.matched_logo is not None or
                any(warning.startswith('Logo') for warning in result.warnings)
            ),
        }
        stages_ok = True
        for stage_name, executed in stage_evidence.items():
            print(f'  {"OK  " if executed else "NG  "} {stage_name}', flush=True)
            if executed is False:
                stages_ok = False

        if stages_ok is False:
            print(
                'ネイティブバイナリのいずれかが起動していません。'
                'ランタイムのビルドまたは配置に問題があります。',
                flush = True,
            )
            return 1

        # 解析が完走した場合はもちろん成功
        if result.status == 'completed':
            print('CM 解析が完走しました。CM 解析ランタイムは正常に動作しています。', flush=True)
            return 0

        # 完走しなかった場合でも、原因が合成素材の性質によるものであれば検証としては成功とする
        ## 本スクリプトの目的はランタイムが動作することの確認であり、検出精度の評価ではない
        if result.error_code in CONTENT_DEPENDENT_ERROR_CODES:
            print(
                f'全てのネイティブバイナリが正常に動作しましたが、合成素材のため'
                f'CM 区間を確定できませんでした。[error_code: {result.error_code}]\n'
                f'これは想定内であり、ランタイム自体は正常です。'
                f'実際の検出精度は実録画でのみ評価できます。',
                flush = True,
            )
            return 0

        # それ以外の失敗は、ランタイムまたは実行環境の問題として扱う
        print(
            f'CM 解析が想定外の理由で失敗しました。'
            f'[status: {result.status}] [error_code: {result.error_code}]',
            flush = True,
        )
        return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('runtime_directory', type=Path, help='ビルド済み CMAnalysis ランタイムのディレクトリ')
    parser.add_argument('--ffmpeg', type=Path, default=Path('/usr/bin/ffmpeg'))
    parser.add_argument('--ffprobe', type=Path, default=Path('/usr/bin/ffprobe'))
    parser.add_argument('--fixture-script', type=Path, required=True)
    args = parser.parse_args()

    sys.exit(asyncio.run(Verify(
        args.runtime_directory.resolve(),
        args.ffmpeg.resolve(),
        args.ffprobe.resolve(),
        args.fixture_script.resolve(),
    )))


if __name__ == '__main__':
    main()
