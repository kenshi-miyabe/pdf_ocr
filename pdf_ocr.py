#!/usr/bin/env python3
"""
OCR PDF files via LM Studio's OpenAI-compatible API.

Usage:
    python pdf_ocr.py /path/to/file.pdf
    python pdf_ocr.py /path/to/pdf_directory

Environment variables:
    LMSTUDIO_BASE_URL   Base URL for LM Studio API (default: http://127.0.0.1:1234/v1)
    LMSTUDIO_API_KEY    Optional API key for OpenAI-compatible servers (default: lm-studio)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import fitz
import requests
import yaml


DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("ocr_config.yml")
DEFAULT_OUTPUT_EXTENSION = ".md"
MAX_OCR_OUTPUT_CHARS = 5000
THINKING_FIELD_NAMES = {
    "reasoning_content",
    "reasoning",
    "thinking",
    "reasoning_text",
}
DEFAULT_PROMPT = (
    "PDF のページ画像に対して OCR を行ってください。"
    "読める文字を自然な順序で忠実に抽出し、結果は Markdown で出力してください。"
    "要約・翻訳・言い換え・補足説明・創作はしないでください。"
    "見出し、箇条書き、表、段落構造は可能な範囲で Markdown として保ってください。"
    "数式はインラインなら $...$、別行なら $$...$$ の TeX 形式で記述してください。"
)
DEFAULT_REVIEW_PROMPT = (
    "# Role: 数学教育エキスパート\n"
    "OCR の誤字を文脈で補完しながら、学生の答案を分析し、"
    "どこで詰まったか、どう解決すべきかを簡潔に助言してください。"
    "点数は付けないでください。\n\n"
    "# Input\n"
    "- 問題: 下に与えられる Problem\n"
    "- 答案(OCR): 下に与えられる Student Answer (OCR)\n\n"
    "# Output Format\n"
    "## 1．推測される解答プロセス\n"
    "(LaTeX を用いて数式ステップを再構成)\n\n"
    "## 2．どこで詰まったか (ボトルネック)\n"
    "- 箇所:\n"
    "- 原因: (知識不足 / 計算ミス / 戦略ミス)\n\n"
    "## 3．解決に向けた処方箋\n"
    "- 次のステップ: (今すぐ何をすべきか)\n"
    "- 復習ポイント: (思い出すべき公式・概念)\n\n"
    "最終出力は日本語で、与えられたテキストに基づいて記述してください。"
)


def load_yaml_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {config_path}")

    return data


def normalize_output_extension(value: str) -> str:
    extension = value.strip()
    if not extension:
        raise ValueError("output_extension must not be empty")
    if not extension.startswith("."):
        extension = f".{extension}"
    return extension


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OCR PDF files through LM Studio and save sibling output files."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="PDF file or directory containing PDF files. Defaults to current directory.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LMSTUDIO_BASE_URL", DEFAULT_BASE_URL),
        help=f"LM Studio API base URL. Defaults to {DEFAULT_BASE_URL}.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"YAML config path. Defaults to {DEFAULT_CONFIG_PATH}.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("LMSTUDIO_API_KEY", "lm-studio"),
        help="API key for OpenAI-compatible servers. Defaults to 'lm-studio'.",
    )
    parser.add_argument(
        "-ans",
        "--answer-file",
        help="Problem or reference text file used for review after OCR.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Rasterization DPI for each PDF page. Defaults to 200.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files. By default they are skipped.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1200,
        help="HTTP timeout in seconds for each request. Defaults to 1200.",
    )
    return parser.parse_args()


def pdf_files_in_directory(directory: Path) -> Iterable[Path]:
    return sorted(path for path in directory.iterdir() if path.suffix.lower() == ".pdf")


def resolve_pdf_targets(target: Path) -> list[Path]:
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {target}")

    if target.is_file():
        if target.suffix.lower() != ".pdf":
            raise ValueError(f"File is not a PDF: {target}")
        return [target]

    if target.is_dir():
        return list(pdf_files_in_directory(target))

    raise ValueError(f"Path must be a PDF file or directory: {target}")


def render_page_to_png_data_url(page: fitz.Page, dpi: int) -> str:
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    png_bytes = pixmap.tobytes("png")
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def format_http_error(exc: requests.HTTPError) -> str:
    response = exc.response
    if response is None:
        return str(exc)

    body = response.text.strip()
    if not body:
        return f"{response.status_code} {response.reason}"

    return f"{response.status_code} {response.reason}: {body}"


@dataclass
class ChatCompletionResult:
    content: str
    thinking: str


class ChatCompletionTimeout(requests.Timeout):
    def __init__(self, message: str, *, thinking: str = "") -> None:
        super().__init__(message)
        self.thinking = thinking


def thinking_output_path(pdf_path: Path) -> Path:
    return pdf_path.with_name(f"thinking-{pdf_path.stem}.txt")


def append_thinking_output(
    pdf_path: Path,
    *,
    stage: str,
    reason: str,
    thinking: str,
) -> None:
    if not thinking.strip():
        return

    path = thinking_output_path(pdf_path)
    entry = (
        f"\n\n===== {stage}: {reason} =====\n"
        f"{thinking.strip()}\n"
    )
    with path.open("a", encoding="utf-8") as file:
        file.write(entry)
    print(f"[THINKING WRITE] {path.name}", file=sys.stderr, flush=True)


def extract_text_parts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        text = value.get("text") or value.get("content")
        return [text] if isinstance(text, str) else []
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return parts
    return []


def extract_thinking_parts(value: Any) -> list[str]:
    parts: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in THINKING_FIELD_NAMES:
                parts.extend(extract_text_parts(nested))
                if isinstance(nested, (dict, list)):
                    parts.extend(extract_thinking_parts(nested))
            elif isinstance(nested, (dict, list)):
                parts.extend(extract_thinking_parts(nested))
    elif isinstance(value, list):
        for item in value:
            parts.extend(extract_thinking_parts(item))
    return parts


def parse_stream_data_line(line: str | bytes) -> dict | None:
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    if not line.startswith("data:"):
        return None

    data = line.removeprefix("data:").strip()
    if not data or data == "[DONE]":
        return None

    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def chat_completion(
    session: requests.Session,
    *,
    base_url: str,
    api_key: str,
    messages: list[dict],
    timeout: int,
    extra_body: dict | None = None,
) -> ChatCompletionResult:
    payload = {
        "messages": messages,
        "temperature": 0,
    }
    if extra_body:
        payload.update(extra_body)
    payload["stream"] = True

    content_parts: list[str] = []
    thinking_parts: list[str] = []
    try:
        with session.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=timeout,
            stream=True,
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines(decode_unicode=False):
                if raw_line is None:
                    continue
                parsed = parse_stream_data_line(raw_line)
                if parsed is None:
                    continue

                for choice in parsed.get("choices", []):
                    delta = choice.get("delta") or {}
                    message = choice.get("message") or {}
                    content_parts.extend(extract_text_parts(delta.get("content")))
                    content_parts.extend(extract_text_parts(message.get("content")))
                    thinking_parts.extend(extract_thinking_parts(delta))
                    thinking_parts.extend(extract_thinking_parts(message))
    except requests.Timeout as exc:
        raise ChatCompletionTimeout(str(exc), thinking="".join(thinking_parts)) from exc

    return ChatCompletionResult(
        content="".join(content_parts).strip(),
        thinking="".join(thinking_parts),
    )


def ocr_page(
    session: requests.Session,
    *,
    base_url: str,
    prompt: str,
    api_key: str,
    page_image_url: str,
    timeout: int,
) -> ChatCompletionResult:
    return chat_completion(
        session,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": page_image_url}},
                ],
            },
        ],
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


def review_ocr_result(
    session: requests.Session,
    *,
    base_url: str,
    review_prompt: str,
    api_key: str,
    answer_text: str,
    ocr_text: str,
    timeout: int,
) -> ChatCompletionResult:
    review_input = (
        "===== REVIEW PROMPT START =====\n"
        f"{review_prompt}\n"
        "===== REVIEW PROMPT END =====\n\n"
        "===== PROBLEM OR REFERENCE TEXT START =====\n"
        f"{answer_text}\n"
        "===== PROBLEM OR REFERENCE TEXT END =====\n\n"
        "===== STUDENT ANSWER OCR START =====\n"
        f"{ocr_text}\n"
        "===== STUDENT ANSWER OCR END ====="
    )
    return chat_completion(
        session,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        messages=[{"role": "user", "content": review_input}],
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )


def append_review_to_output(output_text: str, review_text: str) -> str:
    base = output_text.rstrip()
    review = review_text.strip()
    return f"{base}\n\n---\n\n## Review\n\n{review}\n"


def append_review_timeout_to_output(output_text: str, timeout: int) -> str:
    base = output_text.rstrip()
    return (
        f"{base}\n\n---\n\n## Review\n\n"
        f"[TIMEOUT] Review request timed out after {timeout} seconds.\n"
    )


def format_page_output(page_number: int, page_text: str) -> str:
    return f"## page {page_number} {len(page_text)}文字\n\n{page_text.strip()}\n"


def format_page_timeout_output(page_number: int, timeout: int) -> str:
    return (
        f"## page {page_number} TIMEOUT\n\n"
        f"[TIMEOUT] OCR request timed out after {timeout} seconds.\n"
    )


def truncate_page_ocr_text(page_text: str) -> str:
    return page_text[:MAX_OCR_OUTPUT_CHARS]


def ocr_pdf(
    pdf_path: Path,
    *,
    session: requests.Session,
    base_url: str,
    prompt: str,
    api_key: str,
    dpi: int,
    timeout: int,
) -> tuple[str, bool]:
    pages_text: list[str] = []
    skip_output = False
    with fitz.open(pdf_path) as document:
        total_pages = len(document)
        for index, page in enumerate(document, start=1):
            print(
                f"[OCR] {pdf_path.name}: page {index}/{total_pages}",
                file=sys.stderr,
                flush=True,
            )
            image_url = render_page_to_png_data_url(page, dpi)
            # OCR requests are sent one page at a time; the next page waits for
            # the current page response so a single LM Studio server is not hit
            # with concurrent page requests from this process.
            try:
                page_result = ocr_page(
                    session,
                    base_url=base_url,
                    prompt=prompt,
                    api_key=api_key,
                    page_image_url=image_url,
                    timeout=timeout,
                )
                page_text = page_result.content
            except ChatCompletionTimeout as exc:
                append_thinking_output(
                    pdf_path,
                    stage=f"OCR page {index}",
                    reason=f"timeout after {timeout}s",
                    thinking=exc.thinking,
                )
                pages_text.append(format_page_timeout_output(index, timeout))
                print(
                    f"[OCR PAGE TIMEOUT] {pdf_path.name}: page {index}/{total_pages} "
                    f"(timeout after {timeout}s)",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            except requests.Timeout:
                pages_text.append(format_page_timeout_output(index, timeout))
                print(
                    f"[OCR PAGE TIMEOUT] {pdf_path.name}: page {index}/{total_pages} "
                    f"(timeout after {timeout}s)",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            original_page_chars = len(page_text)
            page_text = truncate_page_ocr_text(page_text)
            if len(page_text) == 0:
                append_thinking_output(
                    pdf_path,
                    stage=f"OCR page {index}",
                    reason="blank response",
                    thinking=page_result.thinking,
                )
            pages_text.append(format_page_output(index, page_text))
            print(
                f"[OCR PAGE DONE] {pdf_path.name}: page {index}/{total_pages} "
                f"({len(page_text)} chars)",
                file=sys.stderr,
                flush=True,
            )
            if original_page_chars > len(page_text):
                print(
                    f"[OCR TRUNCATED] {pdf_path.name}: page {index} limited OCR "
                    f"output to {MAX_OCR_OUTPUT_CHARS} chars",
                    file=sys.stderr,
                    flush=True,
                )
            if index in {1, 2} and len(page_text) == 0:
                print(
                    f"[SKIP] {pdf_path.name}: page {index} OCR output is 0 chars; "
                    "skip markdown and review",
                    file=sys.stderr,
                    flush=True,
                )
                skip_output = True
                break
    return "\n\n".join(pages_text).strip() + "\n", skip_output


def main() -> int:
    args = parse_args()
    target = Path(args.target).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()

    try:
        config = load_yaml_config(config_path)
    except Exception as exc:
        print(f"[ERROR] Failed to read config {config_path}: {exc}", file=sys.stderr)
        return 1

    prompt = str(config.get("prompt") or DEFAULT_PROMPT)
    review_prompt = str(config.get("review_prompt") or DEFAULT_REVIEW_PROMPT)
    try:
        output_extension = normalize_output_extension(
            str(config.get("output_extension") or DEFAULT_OUTPUT_EXTENSION)
        )
    except ValueError as exc:
        print(f"[ERROR] Invalid output_extension in {config_path}: {exc}", file=sys.stderr)
        return 1

    try:
        pdf_files = resolve_pdf_targets(target)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if not pdf_files:
        print(f"No PDF files found in {target}", file=sys.stderr)
        return 0

    session = requests.Session()
    answer_text = None
    if args.answer_file:
        answer_path = Path(args.answer_file).expanduser().resolve()
        if not answer_path.exists() or not answer_path.is_file():
            print(f"[ERROR] Answer file not found: {answer_path}", file=sys.stderr)
            return 1
        answer_text = answer_path.read_text(encoding="utf-8")

    for pdf_path in pdf_files:
        output_path = pdf_path.with_suffix(output_extension)
        markdown_output_path = pdf_path.with_suffix(".md")
        if (
            not args.overwrite
            and (output_path.exists() or markdown_output_path.exists())
        ):
            existing_path = output_path if output_path.exists() else markdown_output_path
            print(f"[SKIP] {existing_path.name} already exists", file=sys.stderr)
            continue

        ocr_started_at = time.perf_counter()
        try:
            text, skip_output = ocr_pdf(
                pdf_path,
                session=session,
                base_url=args.base_url,
                prompt=prompt,
                api_key=args.api_key,
                dpi=args.dpi,
                timeout=args.timeout,
            )
        except requests.Timeout as exc:
            print(
                f"[ERROR] Timeout while processing {pdf_path.name}: {exc}",
                file=sys.stderr,
            )
            return 1
        except requests.HTTPError as exc:
            print(
                f"[ERROR] HTTP error while processing {pdf_path.name}: {format_http_error(exc)}",
                file=sys.stderr,
            )
            return 1
        except requests.RequestException as exc:
            print(
                f"[ERROR] Request failed while processing {pdf_path.name}: {exc}",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:  # pragma: no cover - defensive CLI fallback
            print(f"[ERROR] Failed to process {pdf_path.name}: {exc}", file=sys.stderr)
            return 1

        ocr_elapsed = time.perf_counter() - ocr_started_at
        print(f"[OCR DONE] {pdf_path.name} ({ocr_elapsed:.2f}s)", file=sys.stderr)
        if skip_output:
            continue

        if answer_text is not None:
            review_started_at = time.perf_counter()
            try:
                review_result = review_ocr_result(
                    session,
                    base_url=args.base_url,
                    review_prompt=review_prompt,
                    api_key=args.api_key,
                    answer_text=answer_text,
                    ocr_text=text,
                    timeout=args.timeout,
                )
                review = review_result.content
                if not review:
                    append_thinking_output(
                        pdf_path,
                        stage="Review",
                        reason="blank response",
                        thinking=review_result.thinking,
                    )
            except ChatCompletionTimeout as exc:
                append_thinking_output(
                    pdf_path,
                    stage="Review",
                    reason=f"timeout after {args.timeout}s",
                    thinking=exc.thinking,
                )
                text = append_review_timeout_to_output(text, args.timeout)
                output_path.write_text(text, encoding="utf-8")
                print(
                    f"[REVIEW TIMEOUT] {pdf_path.name} (timeout after {args.timeout}s)",
                    file=sys.stderr,
                )
                continue
            except requests.Timeout:
                text = append_review_timeout_to_output(text, args.timeout)
                output_path.write_text(text, encoding="utf-8")
                print(
                    f"[REVIEW TIMEOUT] {pdf_path.name} (timeout after {args.timeout}s)",
                    file=sys.stderr,
                )
                continue
            except requests.HTTPError as exc:
                print(
                    f"[ERROR] HTTP error while reviewing {pdf_path.name}: {format_http_error(exc)}",
                    file=sys.stderr,
                )
                return 1
            except requests.RequestException as exc:
                print(
                    f"[ERROR] Request failed while reviewing {pdf_path.name}: {exc}",
                    file=sys.stderr,
                )
                return 1

            review_elapsed = time.perf_counter() - review_started_at
            print(f"[REVIEW DONE] {pdf_path.name} ({review_elapsed:.2f}s)", file=sys.stderr)
            text = append_review_to_output(text, review)

        output_path.write_text(text, encoding="utf-8")
        print(f"[WRITE] {output_path.name}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
