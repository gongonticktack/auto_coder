# Fretlab

## 音源分離

サイドバーの「音源分離」から音声ファイル（最大 100 MB）をアップロードすると、Demucs `htdemucs_6s` でボーカル・ベース・ドラム・ギター・ピアノ・その他の6パートに分けます。完了後は各パートを試聴し、192 kbps の MP3 として個別にダウンロードできます。TAB 生成とは独立したジョブで、TAB の音符推定や歌詞認識は行いません。処理結果は `data/jobs/<job-id>` に保存されます。

「その他」には複数の楽器が混ざる場合があります。分離品質は音源によって変わります。

## 拍に合わせた TAB 生成

TAB 生成では分離したドラム（取得できない場合は元音源）から BPM と拍の位置を推定します。ベース・ギター・ピアノ・その他の和声パートを合わせてコード進行を拍ごとに推定します。さらに原曲の拍ごとの音量と裏拍の打音を調べ、静かな場面では低音・高音のピッキング、盛り上がる場面では強弱をつけたダウン／アップストロークや短いミュートを使って伴奏を生成します。コードの切り替わりは優先して鳴らします。生成した強弱は試聴音声と MIDI に反映します。小節線、BPM 表示、MusicXML / MIDI のテンポにも推定値を反映します。拍を安定して検出できない場合は BPM を未検出と表示し、120 BPM の仮グリッドで伴奏を配置します。拍子は 4/4 の表示用グリッドです。

許可された音源から弾き語り用のギター伴奏 TAB を作り、原音と聴き比べながらコード進行と押さえ方を修正するローカル Web アプリです。[技術調査と構成案](docs/guitar-tab-generation-research.md)を元に実装しています。

## 技術構成

| 場所 | 言語・フレームワーク / ライブラリ | 役割 |
| --- | --- | --- |
| `src/App.tsx`, `src/types.ts` | TypeScript、React | アップロード、解析区間・チューニングの設定、進捗表示、左右比較再生、伴奏 TAB 編集。歌詞・コード・配置時刻・6 弦の押さえ方を扱います。 |
| `src/ChordChart.tsx` | React、SVG | 音声から推定した基本コードと歌詞を譜面に並べ、各弦のフレットや歌詞を修正できます。 |
| `vite.config.ts`, `package.json` | Vite | 開発用 Web サーバー、React/TypeScript のビルド、`/api` から FastAPI への転送。 |
| `src/styles.css` | CSS | ダーク UI と形が変化するビジュアル、画面幅に応じたレイアウト。 |
| `src/App.tsx`, `src/chordAudio.ts` | `lucide-react`、ブラウザーの `<audio>` と Web Audio API | アイコン、5種類の音源の左右独立再生、録音サンプルによるアコースティックギターのコード試聴。 |
| `src/App.tsx`, `scripts/copy-font.mjs` | [alphaTab](https://docs.alphatab.net/) | 編集済みノートから alphaTex を組み立てて譜面プレビューを描画。フォントを `public/alphatab/font` に配置します。音声解析には使用しません。 |
| `backend/main.py` | Python 3.11、FastAPI、Pydantic、`python-multipart`、Uvicorn | 音源アップロード、ジョブ状態 API、ノートと歌詞・コード図の保存、音声配信、書き出し API。`BackgroundTasks` で解析を実行します。 |
| `backend/main.py` | `imageio-ffmpeg` と FFmpeg | pip で入る FFmpeg 実行ファイルを使い、音源全体または指定区間を 22,050 Hz・モノラル WAV に正規化します。システム全体の PATH への FFmpeg インストールは不要です。 |
| `backend/main.py` | PyTorch / [Demucs `htdemucs_6s`](https://github.com/facebookresearch/demucs) | 44.1 kHz ステレオの音源を2回の時間シフト推定と50%オーバーラップで分離し、`guitar` と `vocals` ステムを作ります。音符推定の入力だけ22.05 kHzモノラルに変換します。`FRETLAB_SKIP_DEMUCS=1` では元音を使います。 |
| `backend/chords.py`, `backend/arrangement.py` | NumPy、コード候補と伴奏編曲 | 和声パートの音高分布からコード進行を推定し、押さえ方を拍上のストロークとして TAB の音符に変換します。 |
| `backend/exporters.py` | Python 標準ライブラリ | 修正済みノートから、弦・フレット情報を含む MusicXML と MIDI を生成します。 |

処理の順序は **音源アップロード → FFmpeg で正規化 → Demucs でパートを分離 → ベース・ギター・ピアノ・その他を和声音源に合成 → BPM と拍を推定 → コード進行を推定 → ギター伴奏 TAB に編曲 → ボーカルの歌詞認識 → 表示・修正 → MusicXML / MIDI 書き出し**です。初期状態ではアップロードした音源全体を解析します。「指定した区間だけ生成」にチェックを入れた場合のみ開始・終了位置（秒）を指定できます。長い音源は解析時間とディスク使用量が増えます。歌詞認識には faster-whisper の多言語 small モデルを使い、初回解析時にモデルを取得します。

## 歌詞・コード図の譜面

Tab editor の **歌詞・コード** タブで、再生位置にコードを追加します。コード名、歌詞、配置秒数、6 弦から 1 弦までのフレット（×はミュート）を編集し、**変更を保存**を押すと、そのジョブの `data/jobs/<job-id>/job.json` に記録されます。**Score view** ではコード図と歌詞を並べた譜面を表示し、下に従来の alphaTab による TAB も表示します。デモには表示確認用の歌詞とコードを含めています。

歌詞とコードは音源からの推定結果です。歌唱や伴奏の分離が不完全な場合は誤認識するため、再生しながら修正してください。歌詞認識に失敗しても TAB とコード候補は保存されます。現在の MusicXML / MIDI 書き出しは音符と運指を対象とし、歌詞とコード図は含みません。

音源再生は左右比較に固定し、新しい解析後は左右とも原曲を選びます。左右のプルダウンから **原曲**、**コード推定用の和声パート**、**生成したギター伴奏**、**分離したギター**、**ボーカル**、**その他の BGM** を個別に選べます。生成伴奏の試聴は [FreePats Spanish Classical Guitar](https://freepats.zenvoid.org/Guitar/acoustic-guitar.html) の CC0 録音サンプルを使い、生成したストロークを拍に合わせて鳴らします。WAV で保存できます。元演奏の奏法を再現する機能ではありません。

コードと歌詞の表示は秒数に比例した時間軸を使い、赤い再生線が一定速度で進みます。歌詞は認識した発話開始時刻に配置します。和声音源の無音区間は `N.C.`（休）と表示します。コード進行を編集して保存すると、伴奏 TAB も再生成されます。既存の解析結果へ新しい推定方式を適用するには、音源を再解析してください。

## AI モデルの実装範囲

現在使う推定モデルは **Demucs `htdemucs_6s`** と **faster-whisper の多言語 small モデル**です。Demucs の重みは初回起動時、Whisper の重みは初回解析時に取得します。コード進行の推定は和声音源の音高分布と拍グリッドに基づき、TAB の音符は `backend/arrangement.py` がコード図から生成します。生成後に弦・フレットやコード図を修正できます。

以前のギター単音推定コードは TAB 生成経路では使いません。デモセッションの伴奏音はサンプルデータです。

## Windows で起動

64 ビット Windows の x64 PC で、フォルダ直下の **[start.bat](start.bat) をダブルクリック**します。初回はインターネット接続と十分な空き容量が必要です。準備が完了すると `http://127.0.0.1:5173/` がブラウザーで開きます。

`start.bat` は次を確認し、不足しているものを自動で取得・インストールします。

1. Node.js 20 以上。見つからない場合は公式 Node.js の Windows x64 ZIP を `.runtime` に展開し、公開 SHA-256 一覧で照合します。
2. `package-lock.json` に従って npm パッケージを `node_modules` にインストールします。
3. Python 3.10/3.11 の仮想環境。見つからない場合は、SHA-256 を照合した Python 3.11.9 の公式アプリ用 ZIP を `.runtime/python311` に展開し、`.runtime/venv` を作ります。システムへの Python インストールは行いません。
4. `backend/requirements.txt` の Python パッケージを pip でインストールします。これには FastAPI、Demucs、PyTorch、librosa、faster-whisper、FFmpeg 実行ファイルを含む `imageio-ffmpeg` が含まれます。
5. Demucs `htdemucs_6s` の重みを `.runtime/huggingface` に取得します。FFmpeg 実行ファイルも検証します。
6. API と Web サーバーを起動し、両方の応答を確認してからブラウザーを開きます。

起動後もコンソールは開いたままになり、閉じると API と Web サーバーも終了します。API のポート 8000 が使用中なら 8001〜8010 の空きポートを選びます。ダウンロードしたランタイムやログは `.runtime`、アップロード音源とジョブ結果は `data/jobs` に保存します。準備や起動に失敗した場合はランチャーに原因を表示し、サーバーログは `.runtime/logs` に残します。再実行時は揃っている依存を再利用します。

既存の対応 Python を使いたい場合は、起動前に環境変数 `FRETLAB_PYTHON` にその `python.exe` の絶対パスを設定できます。分離なしで試す場合は `FRETLAB_SKIP_DEMUCS=1` を設定します。

## 手動起動

自動ランチャーを使わない場合は、Node.js 20 以上と Python 3.10/3.11 を用意して次を実行します。FFmpeg は `backend/requirements.txt` の `imageio-ffmpeg` から取得されます。

```powershell
npm install
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

別のターミナルで `npm run dev` を実行します。Vite は `/api` を FastAPI に転送します。

## データ保存と現状の制約

ジョブの状態、音符、編集結果は `data/jobs/<job-id>/job.json` に、音声は同じジョブのディレクトリに保存します。DB と Redis/RQ はまだ使っていません。ジョブは FastAPI プロセス内のバックグラウンドタスクなので、API を再起動した場合、進行中ジョブの自動再開はできません。

MusicXML の音価は推定 BPM と 4/4・16 分音符グリッドで仮整形しています。拍を検出できない場合は 120 BPM を書き出し時の仮値として使います。複雑なテンポや拍子、ベンドなどの奏法自動検出、実曲での精度評価は未対応です。ギター・ピアノなどの分離品質とコード推定の精度は原曲によって変わります。生成した TAB は原音と照らし合わせて確認・修正してください。

音源の取得元と、生成譜面の公開・配布条件は素材ごとに確認してください。
