"""
CORTEXKEEPER agent: triggered on MR merge. Extracts architectural decisions from
the discussion thread and stores them as structured memories in the GitLab wiki.
"""

from datetime import datetime
import json
import logging

from legacy.core.gitlab_client import GitLabClient
from legacy.core.claude_client import ClaudeClient
from legacy.core.memory import MemoryStore

logger = logging.getLogger("cortex.cortexkeeper")


async def run_cortexkeeper(payload: dict) -> None:
    """
    Run the cortexKEEPER agent on a merge request webhook payload. Extracts decisions
    from the MR discussion, sends to Claude for structuring, and saves each as a
    wiki memory. Posts a summary comment on the MR.
    """
    try:
        # — Step 1: Extract data from webhook payload —
        mr_iid = payload["object_attributes"]["iid"]
        mr_title = payload["object_attributes"]["title"]
        mr_description = payload["object_attributes"]["description"] or ""
        author_username = payload["user"]["username"]

        # Ensure mr_iid is int for API calls
        mr_iid = int(mr_iid)

        # — Step 2: Initialise clients —
        gitlab = GitLabClient()
        claude = ClaudeClient()
        memory_store = MemoryStore(gitlab)

        # — Step 3: Fetch MR data from GitLab —
        discussions = gitlab.get_mr_discussions(mr_iid)
        changed_files = gitlab.get_mr_changes(mr_iid)

        if not changed_files:
            logger.warning("CORTEXKEEPER: MR !%s has no changed files, skipping", mr_iid)
            return

        # — Step 4: Filter meaningful discussion —
        meaningful = [
            n
            for n in discussions
            if (n.get("body") or "").strip()
            and len((n.get("body") or "").strip()) > 20
            and not (n.get("body") or "").strip().startswith("🧠 CORTEX")
        ]

        description_has_content = len((mr_description or "").strip()) > 50
        if len(meaningful) < 2 and not description_has_content:
            gitlab.post_mr_comment(
                mr_iid,
                "🧠 CORTEX — CORTEXKEEPER\n\n*No meaningful discussion found in this MR to extract decisions from.*",
            )
            return

        # — Step 5: Build the user message for Claude —
        changed_files_block = "\n".join(changed_files)
        discussion_lines = [
            f"[@{n.get('author', '')}] {n.get('body', '')}"
            for n in meaningful
        ]
        discussion_block = "\n".join(discussion_lines)

        user_message = (
            f"MR TITLE: {mr_title}\n"
            f"MR AUTHOR: @{author_username}\n"
            f"MR DESCRIPTION:\n{mr_description}\n\n"
            f"CHANGED FILES:\n{changed_files_block}\n\n"
            f"DISCUSSION THREAD:\n{discussion_block}"
        )

        # — Step 6: Call Claude —
        system_prompt = claude.load_prompt("cortexkeeper")
        response_str = claude.call(system_prompt=system_prompt, user_message=user_message)

        # — Step 7: Parse Claude response —
        # Claude may wrap JSON in markdown code blocks, so extract it first
        json_str = response_str
        if json_str.strip().startswith("```"):
            lines = json_str.strip().split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            json_str = "\n".join(lines)
        
        try:
            decisions = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("CORTEXKEEPER: Failed to parse Claude JSON: %s", e, exc_info=True)
            gitlab.post_mr_comment(
                mr_iid,
                "🧠 CORTEX — CORTEXKEEPER\n\n*Could not parse decision extraction response. Raw response logged for debugging.*",
            )
            return

        if not isinstance(decisions, list):
            decisions = []

        if len(decisions) == 0:
            gitlab.post_mr_comment(
                mr_iid,
                "🧠 CORTEX — CORTEXKEEPER\n\n*No architectural decisions detected in this MR discussion. Nothing stored.*",
            )
            return

        # — Step 8: Save each decision as a memory —
        memory_store.ensure_index_exists()

        saved_memories: list[dict] = []
        for decision in decisions:
            memory_dict = {
                "source_mr_number": str(mr_iid),
                "source_mr_title": mr_title,
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "decision": decision["decision"],
                "rejected": decision.get("rejected", "N/A"),
                "reason": decision["reason"],
                "future_implication": decision["future_implication"],
                "governs_files": decision.get("governs_files", []),
                "decided_by": decision.get("decided_by", [f"@{author_username}"]),
                "confidence": decision.get("confidence", "MEDIUM"),
                "status": "Active",
            }
            memory_store.save_memory(memory_dict)
            saved_memories.append(memory_dict)

        # — Step 9: Post summary comment on the MR —
        wiki_url = gitlab.get_project_wiki_url()
        wiki_link = f"[project wiki]({wiki_url})" if wiki_url else "project wiki"

        summary_lines = [
            "🧠 CORTEX — CORTEXKEEPER",
            "",
            f"Captured {len(saved_memories)} decision(s) from this MR discussion.",
            "",
        ]
        for mem in saved_memories:
            decision_text = mem.get("decision", "")
            governs = ", ".join(mem.get("governs_files") or [])
            mem_id = mem.get("id", "")
            summary_lines.append(f"**Memory #{mem_id}:** {decision_text}")
            summary_lines.append(f"📁 Governs: {governs}")
            summary_lines.append("")

        summary_lines.append(
            "These decisions are now part of your team's institutional memory and will be "
            "checked against all future MRs that touch these files."
        )
        summary_lines.append("")
        summary_lines.append(f"*View all memories in the {wiki_link}.*")

        gitlab.post_mr_comment(mr_iid, "\n".join(summary_lines))

    except Exception as e:
        logger.error("CORTEXKEEPER failed: %s", e, exc_info=True)
        try:
            mr_iid = payload.get("object_attributes", {}).get("iid")
            if mr_iid is not None:
                gitlab = GitLabClient()
                gitlab.post_mr_comment(
                    int(mr_iid),
                    "🧠 CORTEX — CORTEXKEEPER\n\n*An error occurred during decision extraction. Check server logs.*",
                )
        except Exception:
            pass
# Test institutional memory conflict detection
# Conflict detection demo: testing a new retry decision.
# Final institutional memory conflict detection test