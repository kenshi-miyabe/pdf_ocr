# pdf_ocr

PDF ファイルを LM Studio の OpenAI 互換 API で OCR し、同じ場所に Markdown を出力するスクリプトです。

主な機能:

- PDF 1ファイル、またはディレクトリ内の PDF 一式を OCR
- `QA.txt` または `-ans` 指定ファイルを使った review 追記
- LM Studio のモデル一覧表示と、スクリプト側でのモデル指定
- 複数モデルによる再試行
- 同名 `.md` / `.pdf` ペアの zip 作成

## 前提

- `uv` が使えること
- LM Studio で OpenAI 互換 API サーバーが有効であること
- OCR に使うモデルが LM Studio で利用可能であること

`uv` が未導入なら、macOS では次でインストールできます。

```bash
brew install uv
```

## セットアップ

```bash
cd /Users/miyabe/github/pdf_ocr
uv sync
```

`pdf_ocr` コマンドとして使いたい場合は、ラッパーを `/usr/local/bin` に入れます。

```bash
cd /Users/miyabe/github/pdf_ocr
bash scripts/install_pdf_ocr.sh
```

権限が必要な環境では `sudo` を付けます。

```bash
sudo bash scripts/install_pdf_ocr.sh
```

インストール済みのラッパーを更新したい場合も、同じスクリプトを再実行してください。

## 基本的な使い方

対象を省略すると、カレントディレクトリ `.` を処理します。

```bash
pdf_ocr --model <model-id>
pdf_ocr /path/to/file.pdf --model <model-id>
pdf_ocr /path/to/pdf_directory --model <model-id>
```

リポジトリ内から直接実行する場合:

```bash
uv run python pdf_ocr.py . --model <model-id>
```

PDF ファイルを指定した場合はその 1ファイルだけ、ディレクトリを指定した場合は直下の PDF をすべて処理します。出力は各 PDF と同じ場所の同名 `.md` です。既に同名 `.md` がある PDF は `--overwrite` を付けない限りスキップされます。

## モデル指定

使用可能な LM Studio モデル ID は次で確認できます。

```bash
pdf_ocr --lmstudio_models
```

通常実行ではモデル指定が必須です。指定方法は次のいずれかです。

```bash
pdf_ocr --model <model-id>
LMSTUDIO_MODEL=<model-id> pdf_ocr
```

または [ocr_config.yml](/Users/miyabe/github/pdf_ocr/ocr_config.yml) に `model` を書きます。優先順位は `--model`、`LMSTUDIO_MODEL`、YAML の `model` です。

`--model` にはモデル ID の一部も指定できます。完全一致がなければ、その文字列を含むモデルが一意のときだけ採用します。一致なし、または複数一致の場合はエラーになります。

```bash
pdf_ocr --model gemma
```

複数モデルは `,` 区切りで指定できます。

```bash
pdf_ocr --model gemma,glm,qwen
```

この場合、gemma で全 PDF を処理し、次に glm、次に qwen の順で処理します。既に出力ファイルがある PDF はスキップされるため、2つ目以降のモデルでは未成功の PDF だけが処理対象になります。

## Review

`-ans` を指定しない場合、カレントディレクトリに `QA.txt` があれば review に使います。`QA.txt` がなければ review は行わず、OCR 結果だけを保存します。

```bash
pdf_ocr --model <model-id>
```

別の問題文・参照テキストを使う場合は `-ans` を指定します。明示指定したファイルが存在しない場合は、OCR を開始せずエラー終了します。

```bash
pdf_ocr /path/to/file.pdf --model <model-id> -ans /path/to/answerfile.txt
```

review 結果は Markdown の末尾に `## Review` として追記されます。review 用プロンプトは YAML の `review_prompt` で変更できます。

## Zip 作成

同じディレクトリにある同名 `.md` / `.pdf` ペアを zip 化します。OCR やモデル解決は行わず、zip 作成だけで終了します。

```bash
pdf_ocr --zip_pairs
pdf_ocr /path/to/pdf_directory --zip_pairs
```

たとえば `sample.md` と `sample.pdf` があれば `sample.zip` を作成します。`.md` だけ、または `.pdf` だけのファイルはスキップされます。zip には `.md` と `.pdf` の 2ファイルがファイル名だけで格納されます。

## 主なオプション

- `--model`: LM Studio に送るモデル ID、または一意に解決できる部分文字列です。`,` 区切りで複数指定できます
- `--lmstudio_models`: LM Studio の `/models` から使用可能なモデル ID 一覧を表示して終了します
- `--zip_pairs`: 対象ディレクトリ内の同名 `.md` / `.pdf` ペアを zip 化して終了します
- `-ans`, `--answer-file`: review に使う問題文または参照テキストファイルを指定します
- `--overwrite`: 既存の出力ファイルや同名 `.md` がある場合でも上書きします
- `--dpi`: PDF を画像化するときの解像度です。既定値は 200 です
- `--timeout`: API リクエストのタイムアウト秒数です。既定値は 1200 秒です
- `--config`: YAML 設定ファイルを指定します
- `--base-url`: LM Studio API の URL を指定します
- `--api-key`: OpenAI 互換 API 用の API キーを指定します

## YAML 設定

既定では [ocr_config.yml](/Users/miyabe/github/pdf_ocr/ocr_config.yml) を読み込みます。

```yaml
output_extension: .md
model: <model-id>
prompt: |
  OCR 時にモデルへ渡す指示文
review_prompt: |
  review 時にモデルへ渡す指示文
```

別ファイルを使う場合:

```bash
pdf_ocr . --config /path/to/custom.yml --model <model-id>
```

## 環境変数

- `LMSTUDIO_BASE_URL`: 既定値は `http://127.0.0.1:1234/v1`
- `LMSTUDIO_API_KEY`: 既定値は `lm-studio`
- `LMSTUDIO_MODEL`: 使用するモデル ID、または一意に解決できる部分文字列

## 出力とエラー

- OCR 結果は PDF と同じ場所に同名 `.md` として保存します
- 実行ごとに対象ディレクトリへ `log_YYYYMMDDHHMM.txt` を作成し、モデルごとの件数を保存します
- 各ページは `## page N 文字数` の見出し付きで保存します
- page 1 または page 2 の OCR 出力文字数が 0 の場合は、その PDF の Markdown 作成と review をスキップします
- OCR や review の timeout は Markdown に追記される場合があります
- 集計ログには、正常終了、1枚目/2枚目/3枚目以降 OCR の timeout、1枚目/2枚目/3枚目以降 OCR の出力0文字、review の timeout、review の出力0文字、その他のエラーの件数をモデルごとに出力します
- thinking や処理エラーは `thinking-<PDF名>-<model>-<stage>.txt` 形式で保存します
- 同名の thinking ファイルがある場合は `-2`, `-3` のように連番を付けます

## 旧スクリプト

以前の `zip-pairs.sh` は [backup/zip-pairs.sh](/Users/miyabe/github/pdf_ocr/backup/zip-pairs.sh) に退避しています。通常は `pdf_ocr --zip_pairs` を使ってください。
