"""
GUARDKEEPER agent: triggered on MR open or on reply to a GUARDKEEPER comment.
Checks MR against CORTEX memories and posts conflict notice or green check;
handles intentional/accidental/discuss replies.
"""

import json
import logging
import re
from datetime import datetime

from legacy.config import CORTEX_ORG_PROJECT_ID
from legacy.core.gitlab_client import GitLabClient
from legacy.core.claude_client import ClaudeClient
from legacy.core.memory import MemoryStore

logger = logging.getLogger("cortex.guardkeeper")


def _get_memory_by_id(memories: list[dict], memory_id: str) -> dict:
    """
    Find a memory from the list by its id field. Return empty dict if not found.
    Matches ids with or without leading zeros (e.g. 1, 01, 001).
    """
    target = str(memory_id).strip().zfill(3)
    for m in memories:
        if str(m.get("id", "")).strip().zfill(3) == target:
            return m
    return {}


def _parse_conflict_memory_ids_from_discussions(
    discussions: list[dict],
) -> list[tuple[str, bool]]:
    """
    Find the GUARDKEEPER conflict comment in MR discussions and extract Memory #ids.
    Returns list of (memory_id, is_org) tuples, where is_org is True when the match
    was preceded by "Organisation" (i.e. "Organisation Memory #12").

    If the same memory id appears as both "Organisation Memory #N" and plain "Memory #N"
    in the same comment (e.g. in the header and again in Claude's reasoning block),
    the org classification wins — the plain occurrence is suppressed.
    """
    # org_ids: ids seen with is_org=True; all_ids: insertion-ordered {mid: is_org}
    org_ids: set[str] = set()
    all_ids: dict[str, bool] = {}
    for note in discussions:
        body = (note.get("body") or "").strip()
        if "Decision Conflict Detected" not in body or "Memory #" not in body:
            continue
        for match in re.finditer(r"(Organisation\s+)?Memory\s*#\s*(\d+)", body, re.IGNORECASE):
            is_org = bool(match.group(1))
            mid = match.group(2).lstrip("0") or "0"
            if is_org:
                org_ids.add(mid)
            if mid not in all_ids:
                all_ids[mid] = is_org
    # Promote any id seen as org to is_org=True regardless of order
    return [(mid, flag or mid in org_ids) for mid, flag in all_ids.items()]


async def run_guardkeeper(payload: dict, reply_type: str | None = None) -> None:
    """
    Run GUARDKEEPER: Mode 1 (reply_type None) checks MR against memories and posts
    result; Mode 2 (intentional/accidental/discuss) handles developer reply.
    """
    mr_iid: int | None = None
    try:
        if reply_type is not None:
            # — MODE 2: Reply handling —
            mr_iid = int(payload["merge_request"]["iid"])
            note_body = payload["object_attributes"]["note"]
            note_author = payload["user"]["username"]

            gitlab = GitLabClient()

            if reply_type == "intentional":
                # — Step 2: Handle "intentional" — extract reasoning and update memories
                body_lower = (note_body or "").strip().lower()
                idx = body_lower.find("cortex: intentional")
                if idx >= 0:
                    reasoning = (note_body or "")[idx + len("cortex: intentional") :].strip()
                    reasoning = reasoning.lstrip(" —").lstrip(" -").lstrip()
                else:
                    reasoning = ""
                if not reasoning:
                    reasoning = "No reasoning provided."

                # Find our conflict comment and update each conflicted memory
                memory_store = MemoryStore(gitlab)
                discussions = gitlab.get_mr_discussions(mr_iid)
                conflict_items = _parse_conflict_memory_ids_from_discussions(discussions)
                logger.info("GUARDKEEPER intentional: parsed conflict_items=%r", conflict_items)
                override_note = (
                    f"Overridden on {datetime.utcnow().strftime('%Y-%m-%d')} by @{note_author}: {reasoning}"
                )

                # Update project-local memories in this project
                for mid, is_org in conflict_items:
                    if not is_org:
                        logger.info("GUARDKEEPER intentional: updating project memory #%s", mid)
                        try:
                            memory_store.update_memory_status(
                                mid, "Superseded", append_note=override_note
                            )
                        except RuntimeError as e:
                            logger.warning("Could not update memory %s: %s", mid, e)

                # Update org memories in the org project
                org_items = [mid for mid, is_org in conflict_items if is_org]
                if org_items:
                    logger.info(
                        "GUARDKEEPER intentional: updating org memories %r via project_id=%r",
                        org_items, CORTEX_ORG_PROJECT_ID,
                    )
                    try:
                        org_gitlab = GitLabClient(project_id=CORTEX_ORG_PROJECT_ID)
                        for mid in org_items:
                            logger.info("GUARDKEEPER intentional: calling update_org_memory_status for #%s", mid)
                            try:
                                memory_store.update_org_memory_status(
                                    org_gitlab, mid, "Superseded", append_note=override_note
                                )
                            except RuntimeError as e:
                                logger.warning("Could not update org memory %s: %s", mid, e)
                    except Exception as e:
                        logger.warning(
                            "GUARDKEEPER: Could not reach org project for intentional update: %s", e
                        )

                all_ids = [mid for mid, _ in conflict_items]
                gitlab.post_mr_comment(
                    mr_iid,
                    f"🧠 CORTEX — GUARDKEEPER\n\n"
                    f"Acknowledged @{note_author}. This override has been recorded.\n\n"
                    f"**Your reasoning:** {reasoning}\n\n"
                    f"Institutional memory updated for memory/ies: {', '.join('#' + m for m in all_ids) or 'N/A'}. "
                    f"Future developers will see both the original constraint and your override reasoning.",
                )
                return

            if reply_type == "accidental":
                # — Step 3: Handle "accidental" —
                gitlab.post_mr_comment(
                    mr_iid,
                    "🧠 CORTEX — GUARDKEEPER\n\n"
                    f"Understood @{note_author}. This conflict appears to be unintentional.\n\n"
                    "**Next step:** Please revise the implementation to align with the existing "
                    "architectural decision before merging.\n\n"
                    "If you believe the original decision should be revisited, reply with "
                    "`cortex: discuss` to loop in the original decision makers.",
                )
                return

            if reply_type == "discuss":
                # — Step 4: Handle "discuss" —
                memory_store = MemoryStore(gitlab)
                changed_files = gitlab.get_mr_changes(mr_iid)
                memories = memory_store.get_memories_for_files(changed_files)
                usernames: set[str] = set()
                for m in memories:
                    for handle in m.get("decided_by") or []:
                        u = (handle.strip().lstrip("@") or "").strip()
                        if u and u != note_author:
                            usernames.add(u)
                mention_str = " ".join(f"@{u}" for u in sorted(usernames))

                gitlab.post_mr_comment(
                    mr_iid,
                    f"🧠 CORTEX — GUARDKEEPER\n\n"
                    f"Looping in the original decision makers as requested by @{note_author}.\n\n"
                    f"{mention_str}\n\n"
                    "A decision conflict has been flagged on this MR. Your institutional context "
                    "is needed before this merges. Please review the conflict details above "
                    "and share your perspective.",
                )
                return

        # — MODE 1: MR opened — reply_type is None —

        # — Step 1: Extract data from webhook payload —
        mr_iid = int(payload["object_attributes"]["iid"])
        mr_title = payload["object_attributes"]["title"]
        mr_description = payload["object_attributes"]["description"] or ""
        mr_author = payload["user"]["username"]
        mr_url = payload["object_attributes"]["url"]

        # — Step 2: Initialise clients —
        gitlab = GitLabClient()
        claude = ClaudeClient()
        memory_store = MemoryStore(gitlab)

        # — Step 3: Get changed files and full diff —
        changed_files = gitlab.get_mr_changes(mr_iid)
        if not changed_files:
            logger.info("GUARDKEEPER: MR !%s has no changed files, skipping", mr_iid)
            return

        try:
            full_diff = gitlab.get_mr_diff(mr_iid)
        except RuntimeError as e:
            logger.warning("GUARDKEEPER: Could not get MR diff: %s. Proceeding with file list only.", e)
            full_diff = "(Diff unavailable; only file paths were checked.)"

        # — Step 4: Load relevant memories —
        project_memories = memory_store.get_memories_for_files(changed_files)

        # Load org-wide memories from the org project (may be same as GITLAB_PROJECT_ID)
        try:
            org_gitlab = GitLabClient(project_id=CORTEX_ORG_PROJECT_ID)
            org_memories = memory_store.get_all_org_memories(org_gitlab)
        except Exception as e:
            logger.warning("GUARDKEEPER: Could not load org memories: %s", e)
            org_memories = []

        memories = project_memories + org_memories

        if not memories:
            gitlab.post_mr_comment(
                mr_iid,
                "✅ CORTEX — GUARDKEEPER\n\n"
                "**0 memories** found for files in this MR. "
                "No institutional memory to check against yet.\n\n"
                f"*Files scanned: {', '.join(changed_files)}*",
            )
            return

        # — Step 5: Build the user message for Claude (include full diff) —
        changed_files_block = "\n".join(changed_files)
        past_decisions_parts = []
        for m in memories:
            governs = ", ".join(m.get("governs_files") or [])
            is_org = m.get("scope", "").upper() == "ORGANISATION"
            scope_label = "ORG" if is_org else "PROJECT"
            source_project = m.get("source_project", "")
            source_line = f"Source project: {source_project}\n" if source_project else ""
            past_decisions_parts.append(
                f"---\n"
                f"Memory #{m.get('id', '')} [{scope_label}]\n"
                f"Decision: {m.get('decision', '')}\n"
                f"Rejected: {m.get('rejected', '')}\n"
                f"Reason: {m.get('reason', '')}\n"
                f"Future implication: {m.get('future_implication', '')}\n"
                f"Governs files: {governs}\n"
                f"{source_line}"
                f"Memory ID: {m.get('id', '')}\n"
                f"---"
            )
        past_decisions_block = "\n\n".join(past_decisions_parts)

        user_message = (
            f"MR TITLE: {mr_title}\n"
            f"MR AUTHOR: @{mr_author}\n"
            f"MR DESCRIPTION:\n{mr_description}\n\n"
            f"CHANGED FILES:\n{changed_files_block}\n\n"
            f"DIFF (full):\n```\n{full_diff[:50000]}\n```\n\n"
            f"PAST DECISIONS:\n{past_decisions_block}"
        )

        # — Step 6: Call Claude —
        system_prompt = claude.load_prompt("guardkeeper")
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
            result = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("GUARDKEEPER: Failed to parse Claude JSON: %s", e, exc_info=True)
            gitlab.post_mr_comment(
                mr_iid,
                "🧠 CORTEX — GUARDKEEPER\n\n*Could not parse conflict analysis. Check server logs.*",
            )
            return

        has_conflict = result.get("has_conflict", False)
        conflicts = result.get("conflicts") or []
        checked_memories = result.get("checked_memories") or []
        clean_files = result.get("clean_files") or []

        # — Step 8: Post result comment —
        if not has_conflict:
            ids_str = ", ".join(f"#{mid}" for mid in checked_memories)
            clean_files_str = ", ".join(clean_files)
            gitlab.post_mr_comment(
                mr_iid,
                f"✅ CORTEX — GUARDKEEPER\n\n"
                f"**{len(checked_memories)} memories checked. No decision conflicts detected.**\n\n"
                "This MR is clean against your team's institutional memory.\n\n"
                f"*Memories checked: {ids_str}*\n"
                f"*Files scanned: {clean_files_str}*",
            )
            return

        # Build conflict comment with all conflicts
        org_violations = [c for c in conflicts if c.get("memory_id") == "ORG-STANDARDS"]
        memory_conflicts = [c for c in conflicts if c.get("memory_id") != "ORG-STANDARDS"]
        summary_parts = []
        if org_violations:
            summary_parts.append(f"{len(org_violations)} org standard violation(s)")
        if memory_conflicts:
            summary_parts.append(f"{len(memory_conflicts)} architectural decision conflict(s)")
        conflict_parts = [
            "🧠 CORTEX — GUARDKEEPER — ⚠️ Decision Conflict Detected",
            "",
            f"This MR has {' and '.join(summary_parts)}.",
            "",
        ]
        for c in conflicts:
            mem_id = c.get("memory_id", "")
            severity = c.get("severity", "MEDIUM")
            category = c.get("category", "architecture")
            conflict_type = c.get("conflict_type", "direct-contradiction")
            conflict_desc = c.get("conflict_description", "")
            code_location = c.get("conflicting_code_location", "")
            reasoning = c.get("reasoning", "")

            severity_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"}.get(severity, "🟡")
            conflict_type_label = {
                "rejected-approach-reintroduced": "Rejected approach reintroduced",
                "chosen-approach-abandoned": "Chosen approach abandoned",
                "org-standard-violation": "Org standard violation",
                "direct-contradiction": "Direct contradiction",
            }.get(conflict_type, conflict_type)

            is_org_standard = mem_id == "ORG-STANDARDS"
            mem = {} if is_org_standard else _get_memory_by_id(memories, mem_id)
            decision_text = mem.get("decision", "")
            reason_text = mem.get("reason", "")
            decided_by = mem.get("decided_by") or []
            decided_by_str = " ".join(decided_by)
            source_mr = mem.get("source_mr_number", "")
            is_org_memory = mem.get("scope", "").upper() == "ORGANISATION"
            mem_source_project = mem.get("source_project", "")

            conflict_parts.append("---")
            if is_org_standard:
                conflict_parts.append(f"### {severity_emoji} Org Standard Violation — {severity} severity")
            elif is_org_memory:
                org_header = f"### {severity_emoji} Conflict with Organisation Memory #{mem_id} — {severity} severity"
                if mem_source_project:
                    org_header += f"\n**Source project:** {mem_source_project}"
                conflict_parts.append(org_header)
            else:
                conflict_parts.append(f"### {severity_emoji} Conflict with Memory #{mem_id} — {severity} severity")
            conflict_parts.append(f"**Category:** `{category}` | **Type:** {conflict_type_label}")
            conflict_parts.append("")
            conflict_parts.append(f"**What conflicts:** {conflict_desc}")
            conflict_parts.append(f"**Where:** {code_location}")
            conflict_parts.append("")
            conflict_parts.append("**CORTEX's reasoning:**")
            conflict_parts.append(reasoning)
            conflict_parts.append("")
            if not is_org_standard:
                conflict_parts.append("**The original decision:**")
                conflict_parts.append(f"> {decision_text}")
                conflict_parts.append("")
                conflict_parts.append("**Why it was decided:**")
                conflict_parts.append(f"> {reason_text}")
                conflict_parts.append("")
                conflict_parts.append(f"**Original decision makers:** {decided_by_str}")
                conflict_parts.append(f"**Original MR:** !{source_mr}")
            conflict_parts.append("---")
            conflict_parts.append("")

        conflict_parts.append("**Three paths forward — reply to this comment:**")
        conflict_parts.append("")
        conflict_parts.append("💬 `cortex: intentional — [your reasoning]`")
        conflict_parts.append("The new approach is deliberate. CORTEX will update institutional memory with your reasoning.")
        conflict_parts.append("")
        conflict_parts.append("💬 `cortex: accidental`")
        conflict_parts.append("You were unaware of this constraint. Please revise before merging.")
        conflict_parts.append("")
        conflict_parts.append("💬 `cortex: discuss`")
        conflict_parts.append("Loop in the original decision makers before proceeding.")
        conflict_parts.append("")
        conflict_parts.append(f"*CORTEX checked {len(checked_memories)} memories across {len(changed_files)} files.*")

        gitlab.post_mr_comment(mr_iid, "\n".join(conflict_parts))

    except Exception as e:
        logger.error("GUARDKEEPER failed: %s", e, exc_info=True)
        if mr_iid is None:
            try:
                mr_iid = payload.get("object_attributes", {}).get("iid")
                if mr_iid is None:
                    mr_iid = payload.get("merge_request", {}).get("iid")
                if mr_iid is not None:
                    gitlab = GitLabClient()
                    gitlab.post_mr_comment(
                        int(mr_iid),
                        "🧠 CORTEX — GUARDKEEPER\n\n*An error occurred during conflict analysis. Check server logs.*",
                    )
            except Exception:
                pass
        else:
            try:
                gitlab = GitLabClient()
                gitlab.post_mr_comment(
                    mr_iid,
                    "🧠 CORTEX — GUARDKEEPER\n\n*An error occurred during conflict analysis. Check server logs.*",
                )
            except Exception:
                pass
