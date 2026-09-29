# Fretlab

許可された音源からギターの TAB を作り、原音と聴き比べながら弦・フレットを修正するローカル Web アプリです。[技術調査と構成案](docs/guitar-tab-generation-research.md)を元に実装しています。

## 技術構成

| 場所 | 言語・フレームワーク / ライブラリ | 役割 |
| --- | --- | --- |
| `src/App.tsx`, `src/types.ts` | TypeScript、React | アップロード、解析区間・ギターパート・チューニングの設定、進捗表示、再生、TAB 編集。音符イベントに加え、歌詞・コード・配置時刻・6 弦の押さえ方を扱います。 |
| `src/ChordChart.tsx` | React、SVG | 音声から推定した基本コードと歌詞を譜面に並べ、各弦のフレットや歌詞を修正できます。 |
| `vite.config.ts`, `package.json` | Vite | 開発用 Web サーバー、React/TypeScript のビルド、`/api` から FastAPI への転送。 |
| `src/styles.css` | CSS | ダーク UI と形が変化するビジュアル、画面幅に応じたレイアウト。 |
| `src/App.tsx`, `src/chordAudio.ts` | `lucide-react`、ブラウザーの `<audio>` と Web Audio API | アイコン、5種類の音源の左右独立再生、録音サンプルによるアコースティックギターのコード試聴。 |
| `src/App.tsx`, `scripts/copy-font.mjs` | [alphaTab](https://docs.alphatab.net/) | 編集済みノートから alphaTex を組み立てて譜面プレビューを描画。フォントを `public/alphatab/font` に配置します。音声解析には使用しません。 |
| `backend/main.py` | Python 3.11、FastAPI、Pydantic、`python-multipart`、Uvicorn | 音源アップロード、ジョブ状態 API、ノートと歌詞・コード図の保存、音声配信、書き出し API。`BackgroundTasks` で解析を実行します。 |
| `backend/main.py` | `imageio-ffmpeg` と FFmpeg | pip で入る FFmpeg 実行ファイルを使い、音源全体または指定区間を 22,050 Hz・モノラル WAV に正規化します。システム全体の PATH への FFmpeg インストールは不要です。 |
| `backend/main.py` | PyTorch / [Demucs `htdemucs_6s`](https://github.com/facebookresearch/demucs) | 44.1 kHz ステレオの音源を2回の時間シフト推定と50%オーバーラップで分離し、`guitar` と `vocals` ステムを作ります。音符推定の入力だけ22.05 kHzモノラルに変換します。`FRETLAB_SKIP_DEMUCS=1` では元音を使います。 |
| `backend/transcription.py`, `backend/main.py` | [Spotify Basic Pitch](https://github.com/spotify/basic-pitch) の ICASSP 2022 学習済みモデル、TensorFlow、NumPy | 22,050 Hz の WAV を約 2 秒ごとにモデルへ入力し、音高・オンセットの出力を音符の開始・終了時刻と信頼度に変換します。Windows のアプリ制御で Numba の DLL がブロックされる環境でも動くよう、推論モデルを直接呼び出します。弦・フレットはこのモデルからは得られません。 |
| `backend/fingering.py` | 独自の制約付き探索 | 指定チューニングで各音の弦・フレット候補を列挙し、同時発音の弦重複、フレット幅、手の移動を考慮して割り当てます。 |
| `backend/exporters.py` | Python 標準ライブラリ | 修正済みノートから、弦・フレット情報を含む MusicXML と MIDI を生成します。 |

処理の順序は **音源アップロード → FFmpeg で音源全体または指定区間を正規化 → Demucs でギターとボーカルを分離 → Basic Pitch で音符推定 → 運指割当 → 基本コード提案 → ボーカルの歌詞認識 → TAB とコード譜の表示・修正 → MusicXML / MIDI 書き出し**です。初期状態ではアップロードした音源全体を解析します。「指定した区間だけ生成」にチェックを入れた場合のみ開始・終了位置（秒）を指定できます。長い音源は解析時間とディスク使用量が増えます。歌詞認識には faster-whisper の多言語 small モデルを使い、初回解析時にモデルを取得します。

## 歌詞・コード図の譜面

Tab editor の **歌詞・コード** タブで、再生位置にコードを追加します。コード名、歌詞、配置秒数、6 弦から 1 弦までのフレット（×はミュート）を編集し、**変更を保存**を押すと、そのジョブの `data/jobs/<job-id>/job.json` に記録されます。**Score view** ではコード図と歌詞を並べた譜面を表示し、下に従来の alphaTab による TAB も表示します。デモには表示確認用の歌詞とコードを含めています。

歌詞とコードは音源からの推定結果です。歌唱や伴奏の分離が不完全な場合は誤認識するため、再生しながら修正してください。歌詞認識に失敗しても TAB とコード候補は保存されます。現在の MusicXML / MIDI 書き出しは音符と運指を対象とし、歌詞とコード図は含みません。

再生モードは **元音源**、**ギター**、**左右比較**、**コード試聴** です。左右比較では左と右のプルダウンから **原曲**、**ギター**、**コードを弾いた場合**、**ボイス**、**ギター以外の BGM** を個別に選べます。音量スライダーは再生中にも調整できます。コード試聴は保存したコード図の各弦・フレットをチューニングから音高に変換し、[FreePats Spanish Classical Guitar](https://freepats.zenvoid.org/Guitar/acoustic-guitar.html) の CC0 録音サンプルを使ってコード切替時に低音弦から1回ストロークします。コード試聴モードではこの音を WAV で保存できます。元演奏のストロークや奏法を再現する機能ではありません。

コードと歌詞の表示は秒数に比例した時間軸を使い、赤い再生線が一定速度で進みます。歌詞は認識した発話開始時刻に配置します。ギターが鳴っていないと推定した区間は `N.C.`（休）と表示します。既存の解析結果へ新しい無音判定と単語時刻による歌詞配置を適用するには、音源を再解析してください。

## AI モデルの実装範囲

現在動く推定モデルは **Demucs `htdemucs_6s`**、**Basic Pitch の ICASSP 2022 モデル**、**faster-whisper の多言語 small モデル**です。Demucs の重みは初回起動時、Whisper の重みは初回解析時に取得し、Basic Pitch の重みは pip パッケージに同梱されています。Basic Pitch の出力から音符を作る閾値処理は `backend/transcription.py` に実装しています。TAB 上の弦・フレットは `backend/fingering.py` が演奏可能な配置に絞り、ユーザーが修正できます。

調査文書で挙げたギター専用 Audio-to-MIDI モデル、MT3、TabCNN、TART は**まだ組み込んでいません**。学習済み重み、ライセンス、対象音源での精度を確認してから比較対象として追加する設計です。デモセッションの音符と信頼度はサンプルデータです。

## Windows で起動

64 ビット Windows の x64 PC で、フォルダ直下の **[start.bat](start.bat) をダブルクリック**します。初回はインターネット接続と十分な空き容量が必要です。準備が完了すると `http://127.0.0.1:5173/` がブラウザーで開きます。

`start.bat` は次を確認し、不足しているものを自動で取得・インストールします。

1. Node.js 20 以上。見つからない場合は公式 Node.js の Windows x64 ZIP を `.runtime` に展開し、公開 SHA-256 一覧で照合します。
2. `package-lock.json` に従って npm パッケージを `node_modules` にインストールします。
3. Python 3.10/3.11 の仮想環境。見つからない場合は、SHA-256 を照合した Python 3.11.9 の公式アプリ用 ZIP を `.runtime/python311` に展開し、`.runtime/venv` を作ります。システムへの Python インストールは行いません。
4. `backend/requirements.txt` の Python パッケージを pip でインストールします。これには FastAPI、Basic Pitch、Demucs、PyTorch、faster-whisper、FFmpeg 実行ファイルを含む `imageio-ffmpeg` が含まれます。
5. Demucs `htdemucs_6s` の重みを `.runtime/huggingface` に取得します。Basic Pitch の同梱モデルと FFmpeg 実行ファイルも検証します。
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

MusicXML の音価は現在 120 BPM・4/4・16 分音符グリッドで仮整形しています。複雑なテンポや拍子、ベンドなどの奏法自動検出、リードとバッキングの個別分離、実曲での精度評価は未対応です。生成した TAB は原音と照らし合わせて確認・修正してください。

音源の取得元と、生成譜面の公開・配布条件は素材ごとに確認してください。
