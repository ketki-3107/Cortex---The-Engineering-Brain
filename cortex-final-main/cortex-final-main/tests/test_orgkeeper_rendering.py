"""
Unit tests for ORGKEEPER rendering helpers and memory identification logic.
Covers: confirmation comment, conflict comment, ambiguous comment, fast
memory-id extraction, org-index parsing, and org-memory serialisation.
Tests inline the rendering/parsing functions so no live GitLab or Claude
connection is required.
"""
import re
import sys

# ── inline helpers from orgkeeper.py ─────────────────────────────────────────

_MEMORY_REF_RE = re.compile(r"(?:memory\s*#?|#|cortex-memory-)(\d{1,3})", re.IGNORECASE)


def _zero_pad_id(memory_id: str) -> str:
    try:
        n = int(memory_id)
        return f"{n:03d}"
    except (TypeError, ValueError):
        return memory_id.zfill(3) if len(memory_id) < 3 else memory_id


def _serialize_org_memory(memory: dict, project_path: str, promoted_by: str) -> str:
    governs = ", ".join(memory.get("governs_files") or [])
    decided_by = ", ".join(memory.get("decided_by") or [])
    return (
        f"cortex Memory #{memory.get('id', '')}\n"
        f"Source MR: !{memory.get('source_mr_number', '')} — {memory.get('source_mr_title', '')}\n"
        f"Date: {memory.get('date', '')}\n"
        f"Governs files: {governs}\n"
        f"Decision: {memory.get('decision', '')}\n"
        f"Rejected: {memory.get('rejected', '')}\n"
        f"Reason: {memory.get('reason', '')}\n"
        f"Future implication: {memory.get('future_implication', '')}\n"
        f"Decided by: {decided_by}\n"
        f"Confidence: {memory.get('confidence', '')}\n"
        f"Status: {memory.get('status', '')}\n"
        f"Scope: ORGANISATION\n"
        f"Source project: {project_path}\n"
        f"Promoted by: @{promoted_by}\n"
    )


def _parse_org_index(content: str) -> dict:
    index: dict = {}
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3 and parts[1].lower() not in ("file path", "---", ""):
            path = parts[1]
            ids_str = parts[2]
            ids = [i.strip() for i in ids_str.replace(" ", "").split(",") if i.strip()]
            if path and ids:
                index[path] = ids
    return index


def _identify_memory_id_fast(note_body: str, memories: list) -> str | None:
    matches = _MEMORY_REF_RE.findall(note_body)
    if matches:
        candidate = str(int(matches[0]))
        for m in memories:
            if str(int(m.get("id", "0") or "0")) == candidate:
                return m["id"]
    if len(memories) == 1:
        return memories[0]["id"]
    return None


def _build_confirmation_comment(memory, org_memory_id, project_path, promoted_by, today_date):
    governs = ", ".join(f"`{f}`" for f in (memory.get("governs_files") or []))
    lines = [
        "## 🌐 CORTEX — Memory Promoted to Org Layer",
        "",
        f"**Memory #{memory.get('id')}** has been promoted to the organisation-wide memory layer.",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Org Memory ID | CORTEX-ORG-MEMORY-{_zero_pad_id(org_memory_id)} |",
        f"| Decision | {memory.get('decision', '')} |",
        f"| Governs | {governs or '—'} |",
        f"| Confidence | {memory.get('confidence', '—')} |",
        f"| Promoted by | @{promoted_by} |",
        f"| Source project | {project_path} |",
        f"| Promoted on | {today_date} |",
        "",
        "The original project memory has been updated with `Scope: ORGANISATION`.",
        "The org-wide index (`CORTEX-ORG-INDEX`) has been updated.",
        "",
        "*CORTEX ORGKEEPER — org memory promotion agent*",
    ]
    return "\n".join(lines)


def _build_conflict_comment(memory, conflicting_org_id):
    lines = [
        "## ⚠️ CORTEX — Org Promotion Blocked: Duplicate Detected",
        "",
        f"**Memory #{memory.get('id')}** could not be promoted because an existing org memory "
        f"already governs the same files.",
        "",
        f"**Conflicting org memory:** CORTEX-ORG-MEMORY-{_zero_pad_id(conflicting_org_id)}",
        "",
        "If the new decision supersedes the existing org memory, first update that org memory's "
        "status to `Superseded`, then re-run `cortex: promote-to-org`.",
        "",
        "*CORTEX ORGKEEPER — org memory promotion agent*",
    ]
    return "\n".join(lines)


def _build_ambiguous_comment():
    return (
        "## ❓ CORTEX — Promotion Request Unclear\n\n"
        "ORGKEEPER could not determine which memory you want to promote.\n\n"
        "Please re-comment with an explicit reference, e.g.:\n\n"
        "```\ncortex: promote-to-org #004\n```\n\n"
        "*CORTEX ORGKEEPER — org memory promotion agent*"
    )


# ── shared fixtures ───────────────────────────────────────────────────────────

DATE = "2026-08-09"

MEMORY_004 = {
    "id": "004",
    "decision": "Use fixed retry intervals",
    "rejected": "Exponential backoff",
    "reason": "Avoids thundering herd on shared services.",
    "governs_files": ["legacy/agents/cortexkeeper.py", "legacy/agents/guardkeeper.py"],
    "confidence": "HIGH",
    "decided_by": ["@alice"],
    "date": "2026-07-01",
    "status": "Active",
    "source_mr_number": "42",
    "source_mr_title": "Retry strategy overhaul",
    "future_implication": "Retry cap must be revisited if SLA changes.",
}

MEMORY_007 = {
    "id": "007",
    "decision": "Store memories as wiki pages",
    "rejected": "Database tables",
    "reason": "Wiki is already in use.",
    "governs_files": ["legacy/core/memory.py"],
    "confidence": "MEDIUM",
    "decided_by": ["@alice", "@bob"],
    "date": "2026-07-15",
    "status": "Active",
    "source_mr_number": "55",
    "source_mr_title": "Memory store redesign",
    "future_implication": "",
}

ALL_MEMORIES = [MEMORY_004, MEMORY_007]


# ── pytest test functions ─────────────────────────────────────────────────────

def test_confirmation_comment_structure():
    conf = _build_confirmation_comment(MEMORY_004, "003", "myorg/myrepo", "charlie", DATE)
    assert "CORTEX — Memory Promoted to Org Layer" in conf
    assert "**Memory #004**" in conf
    assert "CORTEX-ORG-MEMORY-003" in conf
    assert "Use fixed retry intervals" in conf
    assert "cortexkeeper.py" in conf
    assert "HIGH" in conf
    assert "@charlie" in conf
    assert "myorg/myrepo" in conf
    assert DATE in conf
    assert "Scope: ORGANISATION" in conf
    assert "CORTEX-ORG-INDEX" in conf
    assert "CORTEX ORGKEEPER" in conf


def test_conflict_comment():
    conflict = _build_conflict_comment(MEMORY_004, "001")
    assert "Org Promotion Blocked" in conflict
    assert "Memory #004" in conflict
    assert "CORTEX-ORG-MEMORY-001" in conflict
    assert "Superseded" in conflict
    assert "promote-to-org" in conflict
    assert "CORTEX ORGKEEPER" in conflict


def test_ambiguous_comment():
    ambig = _build_ambiguous_comment()
    assert "Promotion Request Unclear" in ambig
    assert "explicit reference" in ambig
    assert "promote-to-org #004" in ambig
    assert "CORTEX ORGKEEPER" in ambig


def test_fast_id_extraction_explicit():
    assert _identify_memory_id_fast("cortex: promote-to-org #004 please", ALL_MEMORIES) == "004"
    assert _identify_memory_id_fast("cortex: promote-to-org Memory #7", ALL_MEMORIES) == "007"


def test_fast_id_extraction_cortex_memory_form():
    assert _identify_memory_id_fast("please promote CORTEX-MEMORY-004 to org", ALL_MEMORIES) == "004"


def test_fast_id_extraction_single_fallback():
    assert _identify_memory_id_fast("cortex: promote-to-org", [MEMORY_004]) == "004"
    assert _identify_memory_id_fast("cortex: promote-to-org", ALL_MEMORIES) is None


def test_fast_id_extraction_unknown_returns_none():
    assert _identify_memory_id_fast("cortex: promote-to-org #999", ALL_MEMORIES) is None


def test_org_memory_serialisation():
    content = _serialize_org_memory(MEMORY_004, "myorg/myrepo", "charlie")
    assert "cortex Memory #004" in content
    assert "!42" in content
    assert "legacy/agents/cortexkeeper.py" in content
    assert "Use fixed retry intervals" in content
    assert "Exponential backoff" in content
    assert "Scope: ORGANISATION" in content
    assert "Source project: myorg/myrepo" in content
    assert "Promoted by: @charlie" in content
    assert "HIGH" in content
    assert "Active" in content


def test_org_index_parsing():
    org_index_content = (
        "# CORTEX Org Index\n\n"
        "| File Path | Org Memory IDs |\n"
        "| --- | --- |\n"
        "| legacy/agents/cortexkeeper.py | 001, 002 |\n"
        "| legacy/core/memory.py | 003 |\n"
    )
    parsed = _parse_org_index(org_index_content)
    assert "legacy/agents/cortexkeeper.py" in parsed
    assert parsed.get("legacy/agents/cortexkeeper.py") == ["001", "002"]
    assert "legacy/core/memory.py" in parsed
    assert parsed.get("legacy/core/memory.py") == ["003"]
    assert "File Path" not in parsed
    assert "---" not in parsed


def test_org_index_parsing_empty():
    empty_idx = "# CORTEX Org Index\n\n| File Path | Org Memory IDs |\n| --- | --- |\n"
    assert _parse_org_index(empty_idx) == {}


def test_zero_pad_helper():
    assert _zero_pad_id("1") == "001"
    assert _zero_pad_id("42") == "042"
    assert _zero_pad_id("007") == "007"
    assert _zero_pad_id("1000") == "1000"


def test_confirmation_no_governs_files():
    mem_no_files = {**MEMORY_004, "governs_files": []}
    conf_no_files = _build_confirmation_comment(mem_no_files, "005", "org/repo", "dave", DATE)
    assert "| Governs | — |" in conf_no_files


# ── standalone execution (python tests/test_orgkeeper_rendering.py) ───────────

if __name__ == "__main__":
    failures = 0

    def check(name, condition, detail=""):
        global failures
        if condition:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))
            failures += 1

    print("=== Test 1: confirmation comment structure ===")
    conf = _build_confirmation_comment(MEMORY_004, "003", "myorg/myrepo", "charlie", DATE)
    check("heading present", "CORTEX — Memory Promoted to Org Layer" in conf)
    check("memory id in heading", "**Memory #004**" in conf)
    check("org memory id row", "CORTEX-ORG-MEMORY-003" in conf)
    check("decision row", "Use fixed retry intervals" in conf)
    check("governs row shows files", "cortexkeeper.py" in conf)
    check("confidence row", "HIGH" in conf)
    check("promoted by row", "@charlie" in conf)
    check("source project row", "myorg/myrepo" in conf)
    check("promoted on date", DATE in conf)
    check("scope update note", "Scope: ORGANISATION" in conf)
    check("index update note", "CORTEX-ORG-INDEX" in conf)
    check("orgkeeper footer", "CORTEX ORGKEEPER" in conf)

    print()
    print("=== Test 2: conflict comment ===")
    conflict = _build_conflict_comment(MEMORY_004, "001")
    check("conflict heading", "Org Promotion Blocked" in conflict)
    check("memory id mentioned", "Memory #004" in conflict)
    check("conflicting org id shown", "CORTEX-ORG-MEMORY-001" in conflict)
    check("supersede instruction", "Superseded" in conflict)
    check("retry instruction", "promote-to-org" in conflict)
    check("orgkeeper footer", "CORTEX ORGKEEPER" in conflict)

    print()
    print("=== Test 3: ambiguous comment ===")
    ambig = _build_ambiguous_comment()
    check("unclear heading", "Promotion Request Unclear" in ambig)
    check("re-comment instruction", "explicit reference" in ambig)
    check("example syntax shown", "promote-to-org #004" in ambig)
    check("orgkeeper footer", "CORTEX ORGKEEPER" in ambig)

    print()
    print("=== Test 4: fast id extraction — explicit #NNN ===")
    note_a = "cortex: promote-to-org #004 please"
    result_a = _identify_memory_id_fast(note_a, ALL_MEMORIES)
    check("explicit #004 found", result_a == "004")

    note_b = "cortex: promote-to-org Memory #7"
    result_b = _identify_memory_id_fast(note_b, ALL_MEMORIES)
    check("Memory #7 normalised to 007", result_b == "007")

    print()
    print("=== Test 5: fast id extraction — CORTEX-MEMORY-NNN ===")
    note_c = "please promote CORTEX-MEMORY-004 to org"
    result_c = _identify_memory_id_fast(note_c, ALL_MEMORIES)
    check("CORTEX-MEMORY-004 form recognised", result_c == "004")

    print()
    print("=== Test 6: fast extraction — single memory fallback ===")
    note_d = "cortex: promote-to-org"
    result_d = _identify_memory_id_fast(note_d, [MEMORY_004])
    check("single memory returned when no ref", result_d == "004")

    note_e = "cortex: promote-to-org"
    result_e = _identify_memory_id_fast(note_e, ALL_MEMORIES)
    check("None returned when multiple and no ref", result_e is None)

    print()
    print("=== Test 7: fast extraction — unknown id ===")
    note_f = "cortex: promote-to-org #999"
    result_f = _identify_memory_id_fast(note_f, ALL_MEMORIES)
    check("unknown id returns None", result_f is None)

    print()
    print("=== Test 8: org memory serialisation ===")
    content = _serialize_org_memory(MEMORY_004, "myorg/myrepo", "charlie")
    check("memory header line", "cortex Memory #004" in content)
    check("source mr present", "!42" in content)
    check("governs files present", "legacy/agents/cortexkeeper.py" in content)
    check("decision present", "Use fixed retry intervals" in content)
    check("rejected present", "Exponential backoff" in content)
    check("scope: organisation line", "Scope: ORGANISATION" in content)
    check("source project line", "Source project: myorg/myrepo" in content)
    check("promoted by line", "Promoted by: @charlie" in content)
    check("confidence preserved", "HIGH" in content)
    check("status preserved", "Active" in content)

    print()
    print("=== Test 9: org index parsing ===")
    org_index_content = (
        "# CORTEX Org Index\n\n"
        "| File Path | Org Memory IDs |\n"
        "| --- | --- |\n"
        "| legacy/agents/cortexkeeper.py | 001, 002 |\n"
        "| legacy/core/memory.py | 003 |\n"
    )
    parsed = _parse_org_index(org_index_content)
    check("cortexkeeper.py row parsed", "legacy/agents/cortexkeeper.py" in parsed)
    check("two ids for cortexkeeper", parsed.get("legacy/agents/cortexkeeper.py") == ["001", "002"])
    check("memory.py row parsed", "legacy/core/memory.py" in parsed)
    check("memory.py id correct", parsed.get("legacy/core/memory.py") == ["003"])
    check("header row excluded", "File Path" not in parsed)
    check("separator row excluded", "---" not in parsed)

    print()
    print("=== Test 10: org index parsing — empty index ===")
    empty_idx = "# CORTEX Org Index\n\n| File Path | Org Memory IDs |\n| --- | --- |\n"
    parsed_empty = _parse_org_index(empty_idx)
    check("empty index returns empty dict", parsed_empty == {})

    print()
    print("=== Test 11: zero-pad helper ===")
    check("'1' -> '001'", _zero_pad_id("1") == "001")
    check("'42' -> '042'", _zero_pad_id("42") == "042")
    check("'007' -> '007'", _zero_pad_id("007") == "007")
    check("'1000' -> '1000' (no truncation)", _zero_pad_id("1000") == "1000")

    print()
    print("=== Test 12: confirmation — no governs files ===")
    mem_no_files = {**MEMORY_004, "governs_files": []}
    conf_no_files = _build_confirmation_comment(mem_no_files, "005", "org/repo", "dave", DATE)
    check("em-dash shown when no files", "| Governs | — |" in conf_no_files)

    print()
    if failures == 0:
        print("All tests PASSED")
        sys.exit(0)
    else:
        print(f"{failures} test(s) FAILED")
        sys.exit(1)
