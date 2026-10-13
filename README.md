# Fretlab

This project is a local web app that separates audio sources, estimates chords and lyrics, and generates editable guitar TAB accompaniment from a song input.

It combines FFmpeg, Demucs, Whisper, and browser-based editing to help users refine accompaniment tracks from their own recordings.

## 音源分離

サイドバーの「音源分離」から音声ファイル（最大 100 MB）をアップロードすると、Demucs `htdemucs_6s` でボーカル・ベース・ドラム・ギター・ピアノなどの音源を分離できます。
