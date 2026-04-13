# pdf_ocr
PDF ファイル 1 つ、またはディレクトリ内の PDF ファイル一式を OCR し、同じディレクトリに同名の Markdown ファイルを出力するスクリプトです。

## 前提

- `uv` が使えること
- LM Studio で使用したいモデルをロード済みであること
- LM Studio の OpenAI 互換 API が有効であること

`uv` が未導入なら、macOS では以下でインストールできます。

```bash
brew install uv
```

## セットアップ

依存関係をインストールします。

```bash
cd /Users/miyabe/github/pdf_ocr
uv sync
```

## `/usr/local/bin/pdf_ocr` として使う

`pdf_ocr` コマンドを `/usr/local/bin` に置きたい場合は、インストール用スクリプトを実行します。

```bash
cd /Users/miyabe/github/pdf_ocr
bash scripts/install_pdf_ocr.sh
```

`/usr/local/bin` への書き込み権限が必要な環境では、必要に応じて `sudo` を付けてください。

```bash
cd /Users/miyabe/github/pdf_ocr
sudo bash scripts/install_pdf_ocr.sh
```

このシェルスクリプトは次のことを行います。

- `uv` がインストールされているか確認します
- `/usr/local/bin/pdf_ocr` という実行ファイルを作成します
- その実行ファイルの中では `uv run --project /Users/miyabe/github/pdf_ocr python /Users/miyabe/github/pdf_ocr/pdf_ocr.py "$@"` を呼び出すようにします
- 実行権限を付けて、ターミナルから `pdf_ocr ...` で使えるようにします

すでに一度インストールしている場合は、修正版のラッパーに差し替えるためにもう一度このスクリプトを実行してください。

インストール後は、リポジトリへ移動しなくても次のように実行できます。

```bash
pdf_ocr /path/to/pdf_directory
pdf_ocr /path/to/file.pdf
pdf_ocr . --overwrite
pdf_ocr ./pdfs --config /path/to/custom.yml
pdf_ocr -ans /path/to/answerfile.txt /path/to/file.pdf
```

## 実行方法

1. LM Studio を起動する
2. 使用したいモデルをロードする
3. OpenAI 互換 API サーバーを有効化する
4. [ocr_config.yml](/Users/miyabe/github/pdf_ocr/ocr_config.yml) で `prompt` などを必要に応じて編集する
5. 以下のコマンドを実行する

```bash
cd /Users/miyabe/github/pdf_ocr
uv run python pdf_ocr.py /path/to/pdf_directory
uv run python pdf_ocr.py /path/to/file.pdf
```

PDF ファイルを指定した場合はその 1 ファイルだけを処理し、ディレクトリを指定した場合はその中の PDF をすべて処理します。
実行すると、各 PDF と同じ場所に同名の `.md` が作成されます。
同名の `.md` がすでに存在する PDF は、`--overwrite` を付けない限りスキップされます。
各ファイルごとに、OCR 完了時と review 完了時にそれぞれ処理時間が標準エラー出力へ表示されます。

例:

```bash
uv run python pdf_ocr.py .
uv run python pdf_ocr.py ./pdfs
uv run python pdf_ocr.py ./pdfs/sample.pdf
uv run python pdf_ocr.py . --overwrite
uv run python pdf_ocr.py . --dpi 300
uv run python pdf_ocr.py . --config ./ocr_config.yml
uv run python pdf_ocr.py -ans ./answerfile.txt ./pdfs/sample.pdf
```

## オプション

- `--overwrite`: 既存の出力ファイルや同名の `.md` がある場合でも上書きします
- `--dpi`: PDF を画像化するときの解像度です
- `--base-url`: LM Studio API の URL を指定します
- `--config`: `prompt` などを定義した YAML ファイルを指定します
- `--api-key`: OpenAI 互換 API 用の API キーを指定します
- `-ans`, `--answer-file`: OCR 後の講評に使う問題文または参照テキストファイルを指定します
- `--timeout`: ページごとの API リクエストのタイムアウト秒数です

## 講評機能

`-ans` を付けると、OCR のあとに問題文ファイルと OCR 結果をモデルに渡して、学習アドバイス形式の講評を生成します。

```bash
pdf_ocr -ans answerfile.txt pdffile.pdf
```

このとき:

- OCR 結果は通常どおり `.md` などの出力ファイルとして保存されます
- その後、問題文と OCR 結果をもとにしたレビュー結果が同じ Markdown ファイルの末尾に追記されます
- 講評時の指示文は YAML の `review_prompt` で変更できます
- モデルへ渡す際は `review_prompt`、問題文、OCR 答案が開始・終了マーカー付きで明確に区切られます

## YAML 設定

既定では [ocr_config.yml](/Users/miyabe/github/pdf_ocr/ocr_config.yml) を読み込みます。

- `output_extension`: 出力ファイルの拡張子です。`.md` や `.txt` のように指定できます
- `prompt`: OCR 時にモデルへ渡す指示文です
- `review_prompt`: `-ans` 指定時の講評用プロンプトです

モデルの選択は LM Studio 側で行います。このスクリプトは `chat/completions` に `model` を明示的に送らず、LM Studio 側の選択に任せます。

別ファイルを使いたい場合は `--config` を指定します。

```bash
uv run python pdf_ocr.py . --config /path/to/custom.yml
```

## 環境変数

環境変数でも指定できます。

- `LMSTUDIO_BASE_URL` 既定値: `http://127.0.0.1:1234/v1`
- `LMSTUDIO_API_KEY` 既定値: `lm-studio`

例:

```bash
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1 uv run python pdf_ocr.py .
```
