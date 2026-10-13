💻 **ローカルWebアプリ：[Fretlabを開く](http://127.0.0.1:5173/)** — `start.bat`で起動したPC内で利用できます。

# Fretlab（auto_coder）

## 概要

音楽ファイルからパートを分離し、コード・歌詞を推定して、編集可能なギター伴奏TABを作成するローカルWebアプリです。Reactの編集画面とPythonの音声解析APIを組み合わせています。

## 主な機能

- Demucs `htdemucs_6s` によるボーカル・ベース・ドラム・ギター・ピアノなどの分離。
- コード、拍、歌詞の推定とギター伴奏の生成。
- ブラウザ上でのTAB編集・再生。
- MIDI・MusicXMLなどへの書き出し。

## 推奨要件

| 項目 | 環境 |
| --- | --- |
| 簡単起動 | Windows 64-bit / x64、PowerShell |
| Python | 3.10または3.11。起動スクリプトは3.11のローカル導入にも対応 |
| Node.js | 20以上 |
| ブラウザ | 現行のChromeまたはEdge |
| 通信・容量 | 初回のランタイム・ライブラリ・モデル取得用インターネット接続と十分な空き容量 |

音源分離・文字起こしは処理が重いため、余裕のあるメモリとCPUを推奨します。GPU利用は導入するPyTorch・音声モデル環境に依存し、このREADMEではGPUを必須条件としていません。

## 必要なライブラリ

| 分類 | 主な依存関係 |
| --- | --- |
| フロントエンド | React 19、React DOM、alphaTab、lucide-react |
| 開発 | Vite 6、TypeScript 5、React用Viteプラグイン |
| API | FastAPI、Uvicorn、python-multipart |
| 音声処理 | Demucs、NumPy、librosa、faster-whisper、imageio-ffmpeg |

JavaScript依存関係は`package.json`と`package-lock.json`、Python依存関係は`backend/requirements.txt`に記載しています。

## 使い方

### Windowsで起動

1. リポジトリをダウンロードまたはcloneします。
2. ルートの`start.bat`をダブルクリックします。
3. 初回セットアップが完了するまで待ちます。ランタイム・依存関係・分離モデルを準備します。
4. ブラウザで `http://127.0.0.1:5173/` を開きます。
5. 音声を入力し、解析結果を確認してコード・TABを編集、再生、書き出しします。
6. 音源分離だけ使う場合は、サイドバーの「音源分離」から最大100 MBの音声ファイルをアップロードします。

APIは8000〜8010の空きポートを使用します。起動スクリプトのコンソールに実際のポートが表示されます。

### 開発用の手動起動

Python 3.10 / 3.11とNode.js 20以上を準備し、ルートで実行します。

```bash
python -m venv .venv
# OSに応じて .venv を有効化
python -m pip install -r backend/requirements.txt
npm ci
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

別のターミナルで `npm run dev` を実行します。API接続設定は`vite.config.ts`を参照してください。フロントエンドのビルドは `npm run build` です。

## フォルダ構成

| 相対パス | 役割 |
| --- | --- |
| `src/` | React画面、TAB・コード表示、音声再生 |
| `backend/` | API、拍・コード・歌詞解析、伴奏生成、書き出し |
| `backend/requirements.txt` | Python依存関係 |
| `public/samples/` | ギター再生用サンプルと出典・ライセンス |
| `scripts/` | Windows起動とフォント準備 |
| `docs/` | ギターTAB生成の調査資料 |
| `.github/` | 開発ルール・スキル |
| `package.json` | npm依存関係と開発コマンド |
| `start.bat` | Windowsの起動入口 |
| `.runtime/` | 起動時に生成するランタイム、モデルキャッシュ、ログ |
| `data/jobs/` | 実行時に生成するジョブデータ |

## 仕組み

ブラウザから音声をAPIへ渡し、音声の各パートを分離して拍・コード・歌詞を調べます。推定結果からギターの押さえ方と伴奏を組み立て、編集可能なTABとして返します。自動推定のため、完成前に耳と画面で確認・修正してください。

## 確認方法

```bash
npm run build
python -m unittest backend.test_arrangement backend.test_beats
```

## トラブル対処

- 起動失敗：`.runtime/logs/`のAPI・Webログを確認してください。
- 画面が開かない：5173番ポートを使用中のアプリと起動コンソールを確認してください。
- モデル取得失敗：通信を確認して再起動してください。
- 分離を省略して開発する場合は`FRETLAB_SKIP_DEMUCS=1`を指定できます。音源分離の動作確認には使わないでください。

サンプル音源の利用条件は`public/samples/acoustic-guitar/`、開発方針は`contributing.md`を参照してください。
