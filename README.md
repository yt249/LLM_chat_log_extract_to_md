# LLM Chat History Viewer (Codex + Claude)

- Supports `.jsonl` chat logs from Codex (CLI/VS Code) and Claude Code
- Two ways to use: a Python CLI extractor and a web-based viewer/converter

## Overview

Convert LLM `.jsonl` chat logs into readable Markdown with timestamps and roles. Use the CLI to batch‑process folders into timestamped files, or the web UI to preview and download a single or combined Markdown file without installing anything.

## What's Inside

- `viewer.html` — Web UI to load `.jsonl` or `.md`, render nicely, and download Markdown.
- `extract_chat_log.py` — Python CLI extractor that handles both Codex and Claude `.jsonl` logs and writes Markdown to `generatedMD/`.

## Web UI

- Open `viewer.html` in your browser (no server needed).
- Click “Choose File” and select one or more files:
  - `.jsonl`: parsed, merged, sorted by timestamp, and rendered as Markdown.
  - `.md/.markdown/.txt`: concatenated and rendered.
- Click “Download .md” to save the rendered Markdown.
- Extras: dark/light theme toggle, table of contents, syntax highlighting.

## CLI

Requirements: Python 3.9+

- Single log file
  - `python3 extract_chat_log.py --path /path/to/session.jsonl`
- Entire date folder (recursive)
  - `python3 extract_chat_log.py --path ~/.codex/sessions/2025/11/08 --pattern '*.jsonl'`
- Customize output location/name
  - `python3 extract_chat_log.py --path ~/.codex/sessions --outdir generatedMD --prefix ChatHistory`

Behavior
- Writes to `generatedMD/<prefix>-YYYYmmdd-HHMMSS.md` (no overwrites; auto‑timestamped).
- Handles both Codex and Claude schemas:
  - Top‑level `user/assistant` or nested under `payload.message` (Codex `response_item`).
  - Content items: `text`, `input_text`, `output_text`, `tool_use`, `tool_result`.
  - Timestamps from `timestamp`, `payload.timestamp`, or similar keys.
- Cleans noisy IDE context from user messages (e.g., `<environment_context>…</environment_context>`, “Active file:”, “Open tabs:” sections).

## Why

- Long chat logs are hard to read in default viewers.
- This tool provides a clean Markdown view with TOC and code highlighting, and a CLI for repeatable exports.

## Tech Notes

- Web UI uses Marked.js for Markdown and Highlight.js for code highlighting.
- No frameworks or backend; everything runs locally in your browser.

## Tips

- For big batches, prefer the CLI with a folder path and glob pattern.
- For quick spot‑checks or manual merges, use the web UI and multi‑select `.jsonl` files.
