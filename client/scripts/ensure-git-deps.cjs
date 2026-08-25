/**
 * yarn v1 の git 依存キャッシュ衝突を検知して自動修復する preinstall スクリプト
 *
 * yarn v1 は GitHub などの git 依存パッケージを「パッケージ名 @ package.json の version」をキーにしてキャッシュする。
 * このため、同じ version 番号を名乗る別リポジトリ/別コミットのフォークが存在すると、キャッシュキーが衝突し、
 * 先にキャッシュされた方の内容が誤って再利用されてしまう。
 *
 * 実害の例:
 *   - dplayer は makeding/DPlayer#4f5f7892 (TLV 対応, version 1.32.8) を固定しているが、
 *     過去に tsukumijima/DPlayer#v1.32.8 (TLV 非対応, 同じく version 1.32.8) をインストールした環境では
 *     キャッシュ上の dplayer@1.32.8 が tsukumijima 版のまま再利用され、TLV 再生が壊れる (型チェックも落ちる)。
 *   - web-bml も同様に version 1.0.0 のままコミットだけが変わるため、古いコミットのキャッシュが再利用されうる。
 *
 * ここでは package.json 内の github: 指定 (コミット固定) の依存について、yarn キャッシュの解決先が
 * 固定したリポジトリ/コミットと一致するかを確認し、食い違うキャッシュだけを削除して正しい tarball を
 * 再取得させる。キャッシュが空、もしくは既に正しい内容がキャッシュされている場合は何もしない (no-op)。
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');


/**
 * package.json から github: 指定の git 依存を取り出す
 * @returns {{name: string, repo: string, ref: string}[]} 依存名・owner/repo・ref (コミット or タグ) の配列
 */
function collectGitDependencies() {
    const packageJsonPath = path.join(__dirname, '..', 'package.json');
    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
    // dependencies / devDependencies の両方を対象にする
    const allDependencies = { ...(packageJson.dependencies ?? {}), ...(packageJson.devDependencies ?? {}) };

    const gitDependencies = [];
    for (const [name, spec] of Object.entries(allDependencies)) {
        // 例: 'github:makeding/DPlayer#4f5f7892...' から owner/repo と ref を取り出す
        const match = /github:([^#]+)(?:#(.+))?/i.exec(spec);
        if (match !== null) {
            gitDependencies.push({ name, repo: match[1], ref: match[2] ?? '' });
        }
    }
    return gitDependencies;
}


/**
 * yarn キャッシュ一覧を取得する (失敗時は null)
 * @returns {string[] | null} キャッシュ一覧の各行、取得できなければ null
 */
function readYarnCacheList() {
    try {
        // --pattern を付けず全件取得し、1 回の呼び出しで全 git 依存を突き合わせる
        return execSync('yarn cache list', { encoding: 'utf8' }).split('\n');
    } catch {
        // キャッシュ一覧が取れない環境 (yarn 不在等) では検証をスキップする
        return null;
    }
}


function main() {
    const gitDependencies = collectGitDependencies();
    if (gitDependencies.length === 0) return;

    const cacheLines = readYarnCacheList();
    if (cacheLines === null) return;

    for (const { name, repo, ref } of gitDependencies) {
        // 当該パッケージのキャッシュ行 (行頭がパッケージ名 + 空白) をすべて拾う
        const namePattern = new RegExp('^' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s');
        const rows = cacheLines.filter((line) => namePattern.test(line));
        // 未キャッシュなら install 時に正しく取得されるためスキップする
        if (rows.length === 0) continue;

        // 解決先 URL に固定リポジトリが含まれているか確認する
        const repoMatched = rows.some((row) => row.includes(repo));
        // ref がコミットハッシュのときのみ、解決先 URL にそのコミットが含まれているか確認する
        // (タグ指定の場合、解決先 URL はタグ名ではなくコミットハッシュになるため照合できない)
        const refLooksLikeCommit = /^[0-9a-f]{7,40}$/i.test(ref);
        const refMatched = refLooksLikeCommit === false || rows.some((row) => row.includes(ref));

        // 固定したリポジトリ/コミットと食い違う内容がキャッシュされている場合のみ削除する
        if (repoMatched === false || refMatched === false) {
            console.log(`[ensure-git-deps] Cached "${name}" does not match ${repo}#${ref || '(any)'}; cleaning stale cache to force a correct re-fetch...`);
            try {
                execSync(`yarn cache clean ${name}`, { stdio: 'inherit' });
            } catch (error) {
                // 削除に失敗しても install は続行する (次善策として警告のみ)
                console.warn(`[ensure-git-deps] failed to clean "${name}":`, error.message);
            }
        }
    }
}


try {
    main();
} catch (error) {
    // どんな失敗でも install 自体は止めない (キャッシュ検証は best-effort)
    console.warn('[ensure-git-deps] skipped due to an unexpected error:', error.message);
}
