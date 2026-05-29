"""Write email summaries and updates to an Obsidian vault."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.config import DATA_DIR, UPDATE_WAITING_YAML
from app.schemas import DraftResponse, EmailClassification, NormalizedEmail


class ObsidianWriter:
    """Append structured Markdown updates to Obsidian vault notes."""

    def __init__(self, vault_path: str | Path, data_dir: Path | None = None) -> None:
        self.vault_path = Path(vault_path)
        self.data_dir = data_dir or DATA_DIR

    def _ensure_dir(self, relative: str) -> Path:
        folder = self.vault_path / relative
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _note_path(self, folder: str, name: str) -> Path:
        safe_name = name.replace("/", "-")
        return self._ensure_dir(folder) / f"{safe_name}.md"

    def _append_section(self, path: Path, heading: str, content: str) -> None:
        if not path.exists():
            path.write_text(f"# {path.stem}\n\n", encoding="utf-8")
        existing = path.read_text(encoding="utf-8")
        if heading not in existing:
            existing = existing.rstrip() + f"\n\n{heading}\n"
        path.write_text(existing.rstrip() + "\n\n" + content + "\n", encoding="utf-8")

    def _format_summary_block(
        self,
        email: NormalizedEmail,
        classification: EmailClassification,
        draft_response: DraftResponse | None = None,
    ) -> str:
        date_str = email.received_at[:10] if len(email.received_at) >= 10 else "unknown"
        sender = email.sender_name or email.sender_email
        lines = [
            f"### {date_str} — {email.subject}",
            f"From: [[{classification.contact or sender}]]  ",
            f"Category: {classification.category}  ",
            f"Priority: {classification.priority}  ",
            "",
            "Summary:",
            classification.summary,
            "",
        ]
        if classification.project:
            lines.append(f"Project: [[{classification.project}]]")
        if draft_response and draft_response.should_reply:
            lines.extend(["", "Action:", "- Draft reply prepared for review."])
        return "\n".join(lines)

    def write_email_summary(
        self,
        email: NormalizedEmail,
        classification: EmailClassification,
        draft_response: DraftResponse | None = None,
    ) -> list[str]:
        """Append summaries to relevant notes. Returns list of paths written."""
        written: list[str] = []
        block = self._format_summary_block(email, classification, draft_response)

        if classification.company:
            path = self._note_path("Companies", classification.company)
            self._append_section(path, "## Recent Email Activity", block)
            written.append(str(path.relative_to(self.vault_path)))

        if classification.contact:
            path = self._note_path("Contacts", classification.contact)
            self._append_section(path, "## Recent Email Activity", block)
            written.append(str(path.relative_to(self.vault_path)))

        if classification.project:
            path = self._note_path("Projects", classification.project)
            section = (
                "## Recent Updates"
                if classification.category == "project_update"
                else "## Recent Email Activity"
            )
            self._append_section(path, section, block)
            written.append(str(path.relative_to(self.vault_path)))

        if classification.priority in ("high", "urgent") or classification.needs_human_review:
            inbox_path = self._note_path("Email Assistant", "Inbox Review")
            self._append_section(inbox_path, "## Inbox Items", block)
            written.append(str(inbox_path.relative_to(self.vault_path)))

        if draft_response and draft_response.should_reply:
            draft_path = self._note_path("Email Assistant", "Draft Replies")
            draft_block = (
                f"### {email.subject}\n"
                f"To: {email.sender_email}\n\n"
                f"**Subject:** {draft_response.subject or email.subject}\n\n"
                f"{draft_response.body or '(no body)'}\n"
            )
            self._append_section(draft_path, "## Pending Drafts", draft_block)
            written.append(str(draft_path.relative_to(self.vault_path)))

        return written

    def mark_waiting_item_complete(self, item_id: str, evidence: str) -> None:
        """Update Waiting For note and close item in waiting_for.yaml."""
        waiting_path = self._note_path("Email Assistant", "Waiting For")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        block = (
            f"### {now} — Completed: `{item_id}`\n"
            f"Evidence: {evidence}\n"
        )
        self._append_section(waiting_path, "## Completed Items", block)

        if UPDATE_WAITING_YAML:
            yaml_path = self.data_dir / "waiting_for.yaml"
            if yaml_path.exists():
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                for item in data.get("waiting_for", []):
                    if item.get("id") == item_id:
                        item["status"] = "closed"
                yaml_path.write_text(
                    yaml.dump(data, default_flow_style=False, sort_keys=False),
                    encoding="utf-8",
                )
