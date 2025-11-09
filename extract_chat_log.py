#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
from datetime import datetime


def find_jsonl_files(path: str, pattern: str) -> list[str]:
    base = os.path.expanduser(path)
    if os.path.isfile(base):
        return [base] if base.endswith(".jsonl") else []
    # Directory: recursive search
    search_pattern = os.path.join(base, pattern)
    return sorted(glob.glob(search_pattern, recursive=True))


def normalize_message(data: dict, file_basename: str) -> dict | None:
    """Normalize different log schemas (Claude Code vs Codex CLI).

    Returns a dict with: timestamp, role, content, file, message_id, cwd, session_id
    or None if this line is not a message we want to render.
    """
    # Timestamps can appear under different keys or inside payload
    timestamp = (
        data.get("timestamp")
        or (isinstance(data.get("payload"), dict) and data["payload"].get("timestamp"))
        or data.get("created_at")
        or data.get("time")
        or data.get("ts")
    )

    # Prefer nested message object when present (Claude Code style)
    message_obj = data.get("message") if isinstance(data.get("message"), dict) else None

    # If Codex/CLI response_item wrapper is used, extract from payload
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else None
    if payload and not message_obj and isinstance(payload.get("message"), dict):
        message_obj = payload.get("message")

    # Role may be in nested message, payload, or top-level
    role = None
    if message_obj:
        role = message_obj.get("role")
    if not role and payload:
        role = payload.get("role")
    if not role:
        # Some logs use top-level 'role' or 'type' as role indicator
        role = data.get("role") or data.get("type") or data.get("source")
        # Map variants like 'assistant_response' -> 'assistant'
        if isinstance(role, str):
            rl = role.lower()
            if rl not in {"user", "assistant"}:
                if "assistant" in rl or rl in {"model"}:
                    role = "assistant"
                elif "user" in rl:
                    role = "user"

    # Normalize to user/assistant only; others (e.g., system/tool events) are skipped
    if not role or str(role).lower() not in {"user", "assistant"}:
        return None

    # Content may be in different places and shapes
    content = None
    if message_obj and "content" in message_obj:
        content = message_obj.get("content")
    if content is None and payload and "content" in payload:
        content = payload.get("content")
    if content is None:
        # Some logs put text at top-level
        if "content" in data:
            content = data.get("content")
        elif "text" in data:
            content = data.get("text")
        else:
            # Some streaming events put partial text under 'delta'
            delta = data.get("delta")
            if isinstance(delta, dict) and "content" in delta:
                content = delta.get("content")
            elif isinstance(delta, dict) and "text" in delta:
                content = delta.get("text")
            elif isinstance(delta, str):
                content = delta

    # CWD and session id hints when present
    cwd = (
        data.get("cwd")
        or (payload and payload.get("cwd"))
        or data.get("working_directory")
    )
    session_id = (
        data.get("sessionId")
        or (payload and payload.get("sessionId"))
        or data.get("session_id")
    )

    return {
        "timestamp": timestamp,
        "role": str(role).lower(),
        "content": content if content is not None else "",
        "file": file_basename,
        "message_id": data.get("uuid") or data.get("id") or "",
        "cwd": cwd or "",
        "session_id": session_id or "",
    }


def format_time(ts: str | None) -> str:
    if not ts:
        return "Unknown time"
    try:
        # Handle both ISO with Z and naive strings
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts


def clean_user_text(text: str) -> str:
    if not text:
        return text
    # Remove <environment_context>...</environment_context>
    text = re.sub(r"<environment_context[\s\S]*?</environment_context>", "", text, flags=re.IGNORECASE)

    lines = text.splitlines()
    out: list[str] = []
    skip_bullets = False
    for line in lines:
        # Drop headings or bullets about IDE context
        if re.match(r"^\s*#\s*Context from my IDE setup:", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^\s*##\s*Active file:\s*", line, flags=re.IGNORECASE):
            skip_bullets = False
            continue
        if re.match(r"^\s*##\s*Open tabs:\s*", line, flags=re.IGNORECASE):
            skip_bullets = True
            continue
        if re.match(r"^\s*-\s*Active file:\s*", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^\s*-\s*Open tabs:\s*", line, flags=re.IGNORECASE):
            skip_bullets = True
            continue
        if skip_bullets:
            if re.match(r"^\s*-\s+", line):
                continue
            else:
                skip_bullets = False
        out.append(line)

    # Remove any excess blank lines from removed sections
    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def render_content_blocks(output: list[str], content, role: str = ""):
    """Render content which can be a list (structured), dict, or string."""
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                t = item.get("type")
                if t in ("text", "input_text", "output_text"):
                    text = item.get("text", "")
                    if role == "user":
                        text = clean_user_text(text)
                    if text:
                        output.append(text)
                        output.append("")
                elif t == "tool_use":
                    tool_name = item.get("name", "unknown")
                    tool_input = item.get("input", {})
                    output.append(f"**Tool Use:** `{tool_name}`")
                    output.append("```json")
                    output.append(json.dumps(tool_input, indent=2))
                    output.append("```")
                    output.append("")
                elif t == "tool_result":
                    tool_use_id = item.get("tool_use_id", "unknown")
                    tool_content = item.get("content", "")
                    output.append(f"**Tool Result:** {tool_use_id}")
                    if isinstance(tool_content, str):
                        output.append("```")
                        output.append(
                            tool_content[:1000]
                            + ("..." if len(tool_content) > 1000 else "")
                        )
                        output.append("```")
                    else:
                        output.append("```json")
                        output.append(json.dumps(tool_content, indent=2)[:1000])
                        output.append("```")
                    output.append("")
            elif isinstance(item, str):
                output.append(item)
                output.append("")
            elif isinstance(content, dict):
                # Best-effort pretty print
                output.append("```json")
                output.append(json.dumps(content, indent=2)[:2000])
                output.append("```")
                output.append("")
    elif isinstance(content, str):
        text = content
        if role == "user":
            text = clean_user_text(text)
        if text:
            output.append(text)
            output.append("")


def main():
    parser = argparse.ArgumentParser(description="Extract chat history from Claude/Codex logs")
    parser.add_argument(
        "--path",
        dest="path",
        default="~/.codex/sessions",
        help="Path to a .jsonl file or directory (default: ~/.codex/sessions)",
    )
    parser.add_argument(
        "--pattern",
        default="**/*.jsonl",
        help="Glob pattern under base dir (default: **/*.jsonl)",
    )
    parser.add_argument(
        "--outdir",
        default="generatedMD",
        help="Directory to place generated markdown files (default: generatedMD)",
    )
    parser.add_argument(
        "--prefix",
        default="ChatHistory",
        help="Filename prefix for generated markdown (default: ChatHistory)",
    )
    args = parser.parse_args()

    jsonl_files = find_jsonl_files(args.path, args.pattern)

    if not jsonl_files:
        expanded = os.path.expanduser(args.path)
        where = expanded if os.path.isfile(expanded) else f"{expanded} (pattern {args.pattern})"
        print(f"No .jsonl files found at {where}.")
        print("Tip: verify the date folder and use --path to point to the correct file or session directory.")
        print("Examples: --path ~/.codex/sessions/2025/11/08  or  --path ~/.codex/sessions/2025/11/08/abc.jsonl")

    all_messages: list[dict] = []
    total_lines = 0
    skipped_lines = 0

    for file_path in jsonl_files:
        if not os.path.exists(file_path):
            continue

        print(f"Processing: {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    total_lines += 1
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        print(
                            f"  Warning: Line {line_num} in {file_path} is not valid JSON: {e}"
                        )
                        skipped_lines += 1
                        continue

                    msg = normalize_message(data, os.path.basename(file_path))
                    if msg is None:
                        skipped_lines += 1
                        continue
                    all_messages.append(msg)
        except Exception as e:
            print(f"  Error reading {file_path}: {e}")

    # Sort by timestamp (fallback to empty string if missing)
    all_messages.sort(key=lambda x: x["timestamp"] if x["timestamp"] else "")

    print(f"\nTotal messages extracted: {len(all_messages)}")
    print(f"Total lines scanned: {total_lines}; skipped: {skipped_lines}")

    # Format as markdown
    output = ["# Claude/Codex Chat History", ""]

    current_conversation = None
    message_count = 0

    for msg in all_messages:
        time_str = format_time(msg.get("timestamp"))

        # Start a new conversation section per source file
        if current_conversation != msg["file"]:
            current_conversation = msg["file"]
            output.append(f"\n---\n\n## Conversation: {msg['file']}\n")
            if msg.get("cwd"):
                output.append(f"**Working Directory:** `{msg['cwd']}`\n")
            if msg.get("session_id"):
                output.append(f"**Session ID:** `{msg['session_id']}`\n")

        role = str(msg.get("role", "")).upper() or "UNKNOWN"
        output.append(f"### [{time_str}] {role}\n")
        render_content_blocks(output, msg.get("content"), role=msg.get("role", ""))
        message_count += 1

    output.append(f"\n---\n\n*Total messages: {message_count}*")

    # Prepare output path: generatedMD/<prefix>-YYYYmmdd-HHMMSS.md
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.expanduser(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    output_path = os.path.join(outdir, f"{args.prefix}-{ts}.md")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output))

    print(f"\nChat history written to: {output_path}")
    print(f"Total messages processed: {message_count}")


if __name__ == "__main__":
    main()
