"""
Generates a per-participant activity report package: a full-context
conversation export (every message in every channel/DM the participant took
part in during a date range -- not just their own messages, since making
sense of a conversation needs both sides of it) plus a companion analysis
prompt designed to be pasted into an AI chatbot alongside it.

This module deliberately never calls any AI API itself -- it only prepares
the two files a human hands to whatever chatbot they use.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from slack_msg_reader.export import (
    DEFAULT_MAX_CHARS,
    DEFAULT_MAX_FILES,
    fetch_channel_blocks_for_participant,
    write_blocks,
)

ANALYSIS_PROMPT_TEMPLATE = """\
あなたはSlackでのチームコミュニケーションを分析するアシスタントです。
添付する会話ログ（Markdown、チャンネル/DMごとに時系列で整理されています）を読み、
「{participant}」というユーザーを中心に、以下の観点で日本語で分析してください。

1. 今回の期間中にやったこと
   {participant} が関わった作業・議論・意思決定を、チャンネルごとに要約してください。

2. 新たに発生したタスク
   会話の中で新しく生まれたタスクやToDoを洗い出してください。担当者が分かれば明記してください。

3. 期限
   2で挙げたタスクのうち、期限（いつまでに）が言及されているものを明記してください。
   期限が不明なものは「期限不明」としてください。

4. 良くなかったコミュニケーション
   誤解、行き違い、対応の遅れ、感情的なやり取りなど、改善の余地があるコミュニケーションが
   あれば、該当箇所を引用しつつ指摘してください。

5. 返信漏れ・未対応の案件
   {participant} 宛て、または {participant} が対応すべきと思われるメッセージのうち、
   この会話ログの範囲内で返信・対応が確認できないものを洗い出してください。

対象期間: {since} 〜 {until}
会話ログファイル: {conversation_files}

分からない項目は推測で断定せず、「ログからは判断できません」と正直に書いてください。
"""


@dataclass
class ReportResult:
    conversation_files: list[Path]
    prompt_file: Path | None
    truncated: bool


def generate_report(
    output_dir: Path,
    participant: str,
    since: datetime | None = None,
    until: datetime | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_files: int = DEFAULT_MAX_FILES,
) -> ReportResult:
    """Writes report_conversations*.md (full context) + report_prompt.txt to output_dir."""
    blocks = fetch_channel_blocks_for_participant(participant, since=since, until=until)
    if not blocks:
        return ReportResult(conversation_files=[], prompt_file=None, truncated=False)

    conversation_files, truncated = write_blocks(
        blocks, output_dir, max_chars=max_chars, max_files=max_files, base_name="report_conversations"
    )

    prompt_text = ANALYSIS_PROMPT_TEMPLATE.format(
        participant=participant,
        since=since.date().isoformat() if since else "指定なし",
        until=until.date().isoformat() if until else "指定なし",
        conversation_files=", ".join(p.name for p in conversation_files),
    )
    prompt_file = output_dir / "report_prompt.txt"
    prompt_file.write_text(prompt_text, encoding="utf-8")

    return ReportResult(conversation_files=conversation_files, prompt_file=prompt_file, truncated=truncated)
