from __future__ import annotations

import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from app.logging_utils import format_log_event, get_logger

_logger = get_logger(__name__)

_DEFAULT_SKILL_CMD_CANDIDATES = (
    os.environ.get("SMC_X_POST_FORMAT_CMD", "").strip(),
    os.environ.get("X_POST_FORMAT_CMD", "").strip(),
    r"E:\User Interface Design\x-post-format-skill\scripts\clean-x-post.cmd",
)
_DEFAULT_TIMEOUT_SECONDS = 15.0
_SKILL_BATCH_FILE_NAME = "drafts.md"
_SKILL_OUTPUT_FILE_NAME = "drafts.cleaned.md"
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[\u3002\uff01\uff1f!?])\s+|(?<=\.)\s+(?=[A-Z0-9\"'(\[])")
_EN_TRANSITION_PATTERN = re.compile(
    r"\s+(?=(?:but|however|then|so|meanwhile|result)\b)",
    flags=re.IGNORECASE,
)
_ZH_TRANSITION_PATTERN = re.compile(
    r"\s+(?=(?:\u4f46\u662f|\u4f46|\u4e0d\u8fc7|\u7136\u800c|\u6240\u4ee5|\u56e0\u6b64|\u7136\u540e|\u540c\u65f6|\u53e6\u5916|\u800c\u4e14))",
)


def _resolve_skill_cmd_path() -> Path | None:
    for candidate in _DEFAULT_SKILL_CMD_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists():
            return path
    return None


def _non_whitespace_fingerprint(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _same_non_whitespace(left: str, right: str) -> bool:
    return _non_whitespace_fingerprint(left) == _non_whitespace_fingerprint(right)


def _normalize_line_endings(value: str) -> str:
    return (value or "").replace("\r\n", "\n").replace("\r", "\n")


def _collapse_blank_lines(value: str) -> str:
    compacted = re.sub(r"\n{3,}", "\n\n", value)
    return "\n".join(line.rstrip() for line in compacted.split("\n"))


def _segment_text_layout_only(value: str) -> str:
    text = _normalize_line_endings(value).strip()
    if not text:
        return ""

    if "\n" not in text:
        if re.search(r"[\u3002\uff01\uff1f!?]", text):
            text = re.sub(r"([\u3002\uff01\uff1f!?])\s*", r"\1\n\n", text).strip()
        else:
            segments = [item.strip() for item in _SENTENCE_SPLIT_PATTERN.split(text) if item.strip()]
            if len(segments) > 1:
                text = "\n\n".join(segments)
            else:
                text = _EN_TRANSITION_PATTERN.sub("\n\n", text)
                text = _ZH_TRANSITION_PATTERN.sub("\n\n", text)

    text = _collapse_blank_lines(text)
    candidate = text.strip()
    return candidate if _same_non_whitespace(value, candidate) else value


class XPostFormatter:
    def __init__(
        self,
        *,
        skill_cmd_path: Path | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        enable_skill: bool = True,
    ) -> None:
        resolved_skill_cmd_path = skill_cmd_path or _resolve_skill_cmd_path()
        self._skill_cmd_path = resolved_skill_cmd_path if enable_skill else None
        self._timeout_seconds = max(1.0, float(timeout_seconds))

    @property
    def skill_enabled(self) -> bool:
        return self._skill_cmd_path is not None

    def format_texts(self, texts: list[str], *, request_id: str, route: str) -> list[str]:
        if not texts:
            return []

        layout_only_texts = [_segment_text_layout_only(item) for item in texts]
        if not self.skill_enabled:
            return layout_only_texts

        cleaned_texts = self._run_skill_cleanup_batch(layout_only_texts, request_id=request_id, route=route)
        if not cleaned_texts:
            return layout_only_texts

        merged: list[str] = []
        for raw_text, fallback_text, cleaned_text in zip(texts, layout_only_texts, cleaned_texts, strict=False):
            candidate = cleaned_text if _same_non_whitespace(raw_text, cleaned_text) else fallback_text
            merged.append(candidate)
        return merged

    def _run_skill_cleanup_batch(self, texts: list[str], *, request_id: str, route: str) -> list[str] | None:
        if not self._skill_cmd_path:
            return None

        marker = f"__SMC_DRAFT_MARKER_{uuid.uuid4().hex}__"
        payload_lines: list[str] = []
        for index, text in enumerate(texts):
            payload_lines.append(f"<!--{marker}:{index}-->")
            payload_lines.append(_normalize_line_endings(text).strip())
            payload_lines.append("")
        payload_lines.append(f"<!--{marker}:{len(texts)}-->")
        payload = "\n".join(payload_lines).strip() + "\n"

        with tempfile.TemporaryDirectory(prefix="smc-post-format-") as temp_dir:
            input_path = Path(temp_dir) / _SKILL_BATCH_FILE_NAME
            output_path = Path(temp_dir) / _SKILL_OUTPUT_FILE_NAME
            input_path.write_text(payload, encoding="utf-8")
            try:
                completed = subprocess.run(  # noqa: S603
                    [str(self._skill_cmd_path), str(input_path), str(output_path)],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                _logger.warning(
                    format_log_event(
                        "post_format_skill_timeout",
                        request_id=request_id,
                        route=route,
                        timeout_seconds=self._timeout_seconds,
                    )
                )
                return None
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    format_log_event(
                        "post_format_skill_exec_failed",
                        request_id=request_id,
                        route=route,
                        error=str(exc),
                    )
                )
                return None

            if completed.returncode != 0:
                _logger.warning(
                    format_log_event(
                        "post_format_skill_nonzero_exit",
                        request_id=request_id,
                        route=route,
                        returncode=completed.returncode,
                        stderr=(completed.stderr or "").strip()[:600],
                    )
                )
                return None

            if not output_path.exists():
                _logger.warning(
                    format_log_event(
                        "post_format_skill_missing_output",
                        request_id=request_id,
                        route=route,
                        output_path=str(output_path),
                    )
                )
                return None

            cleaned_payload = output_path.read_text(encoding="utf-8")
            parsed = self._extract_marked_blocks(cleaned_payload, marker=marker, expected=len(texts))
            if parsed is None:
                _logger.warning(
                    format_log_event(
                        "post_format_skill_parse_failed",
                        request_id=request_id,
                        route=route,
                    )
                )
                return None
            return parsed

    @staticmethod
    def _extract_marked_blocks(payload: str, *, marker: str, expected: int) -> list[str] | None:
        marker_pattern = re.compile(rf"<!--{re.escape(marker)}:(\d+)-->")
        matches = list(marker_pattern.finditer(payload or ""))
        if len(matches) < expected + 1:
            return None

        blocks_by_index: dict[int, str] = {}
        for current, nxt in zip(matches, matches[1:], strict=False):
            try:
                index = int(current.group(1))
            except ValueError:
                return None
            if index >= expected:
                continue
            block = payload[current.end() : nxt.start()]
            blocks_by_index[index] = _collapse_blank_lines(_normalize_line_endings(block).strip("\n"))

        if any(index not in blocks_by_index for index in range(expected)):
            return None
        return [blocks_by_index[index] for index in range(expected)]


def build_post_formatter(*, enable_skill: bool = True) -> XPostFormatter:
    return XPostFormatter(enable_skill=enable_skill)
