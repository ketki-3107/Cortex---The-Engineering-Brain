"""
Unit tests for CORTEXCAST issue body rendering logic.
Covers: Decision Intelligence section — hotspots, broad decisions,
confidence/status distribution, coverage recommendation, and the
no-DI fallback (existing health sections remain intact).
"""
import sys


def render_issue_body(result: dict, today_date: str) -> str:
    total_memories = result.get("total_memories", 0)
    healthy_count = result.get("healthy_count", 0)
    review_count = result.get("review_count", 0)
    stale_count = result.get("stale_count", 0)
    health_summary = result.get("health_summary", "")
    top_recommendation = result.get("top_recommendation", "")
    stale_memories = result.get("stale_memories") or []
    review_memories = result.get("review_memories") or []
    di = result.get("decision_intelligence") or {}

    body_parts = [
        f"# 🧠 CORTEX Health Report — {today_date}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total memories | {total_memories} |",
        f"| Healthy | {healthy_count} |",
        f"| Needs review | {review_count} |",
        f"| Potentially stale | {stale_count} |",
        "",
        "## Overall Health",
        health_summary,
        "",
        f"**Top recommendation:** {top_recommendation}",
        "",
    ]

    if di:
        conf = di.get("confidence_distribution") or {}
        status_dist = di.get("status_distribution") or {}
        hotspots = di.get("hotspot_files") or []
        broad = di.get("broad_decisions") or []
        coverage_rec = di.get("coverage_recommendation", "")
        governed_file_count = di.get("governed_file_count", 0)

        body_parts += [
            "",
            "## 🔍 Decision Intelligence",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Files governed by at least one memory | {governed_file_count} |",
            f"| HIGH confidence decisions | {conf.get('HIGH', 0)} |",
            f"| MEDIUM confidence decisions | {conf.get('MEDIUM', 0)} |",
            f"| LOW confidence decisions | {conf.get('LOW', 0)} |",
            f"| Active memories | {status_dist.get('Active', 0)} |",
            f"| Superseded memories | {status_dist.get('Superseded', 0)} |",
            "",
        ]

        if hotspots:
            body_parts += [
                "### Coverage Hotspots",
                "",
                "Files governed by 3 or more memories — potential fragility or high churn:",
                "",
            ]
            for h in hotspots:
                ids_str = ", ".join(f"#{mid}" for mid in (h.get("memory_ids") or []))
                body_parts.append(
                    f"- **{h.get('file', '')}** — {h.get('memory_count', 0)} memories "
                    f"({ids_str}): {h.get('risk_note', '')}"
                )
            body_parts.append("")

        if broad:
            body_parts += [
                "### Architecturally Broad Decisions",
                "",
                "Memories governing 3 or more files — cross-cutting constraints:",
                "",
            ]
            for b in broad:
                files_str = ", ".join(b.get("files") or [])
                body_parts.append(
                    f"- **Memory #{b.get('memory_id', '')}** ({b.get('file_count', 0)} files — "
                    f"{files_str}): {b.get('decision_summary', '')}"
                )
            body_parts.append("")

        if coverage_rec:
            body_parts += [
                "### Coverage Recommendation",
                "",
                coverage_rec,
                "",
            ]

    body_parts.append("")

    if stale_memories:
        body_parts.append("## ⚠️ Stale Memories — Action Required")
        body_parts.append("")
        for s in stale_memories:
            mem_id = s.get("memory_id", "")
            reason_stale = s.get("reason_stale", "")
            urgency = s.get("urgency", "")
            suggested_action = s.get("suggested_action", "")
            body_parts.append(f"### Memory #{mem_id}")
            body_parts.append(f"**Why potentially stale:** {reason_stale}")
            body_parts.append(f"**Urgency:** {urgency}")
            body_parts.append(f"**Suggested action:** {suggested_action}")
            body_parts.append("")

    if review_memories:
        body_parts.append("## 🔍 Memories Worth Reviewing")
        body_parts.append("")
        for r in review_memories:
            mem_id = r.get("memory_id", "")
            reason_review = r.get("reason_review", "")
            suggested_action = r.get("suggested_action", "")
            body_parts.append(f"### Memory #{mem_id}")
            body_parts.append(f"**Why:** {reason_review}")
            body_parts.append(f"**Suggested action:** {suggested_action}")
            body_parts.append("")

    if not stale_memories and not review_memories:
        body_parts.append("## ✅ All Memories Healthy")
        body_parts.append("")
        body_parts.append(
            "No stale or at-risk memories detected. Your institutional memory is in good shape."
        )
        body_parts.append("")

    body_parts.append("## Memory Growth")
    body_parts.append(f"Total memories stored: **{total_memories}**")
    body_parts.append(f"Report generated: {today_date}")
    body_parts.append("")
    body_parts.append("---")
    body_parts.append("*Generated by CORTEX CORTEXCAST — your institutional memory health agent*")
    body_parts.append("*To run another health check: POST /cortexcast*")

    return "\n".join(body_parts)


# ── shared fixtures ───────────────────────────────────────────────────────────

DATE = "2026-08-09"

BASE_RESULT = {
    "total_memories": 5,
    "healthy_count": 3,
    "review_count": 1,
    "stale_count": 1,
    "health_summary": "Memory is growing steadily.",
    "top_recommendation": "Review Memory #002 with @alice.",
    "stale_memories": [],
    "review_memories": [],
}


# ── pytest test functions ─────────────────────────────────────────────────────

def test_no_di_existing_sections_intact():
    out = render_issue_body({**BASE_RESULT}, DATE)
    assert f"CORTEX Health Report — {DATE}" in out
    assert "| Total memories | 5 |" in out
    assert "Memory is growing steadily." in out
    assert "Review Memory #002 with @alice." in out
    assert "Decision Intelligence" not in out
    assert "All Memories Healthy" in out


def test_confidence_and_status_distribution():
    di = {
        "governed_file_count": 8,
        "confidence_distribution": {"HIGH": 3, "MEDIUM": 2, "LOW": 0},
        "status_distribution": {"Active": 4, "Superseded": 1},
        "hotspot_files": [],
        "broad_decisions": [],
        "coverage_recommendation": "",
    }
    out = render_issue_body({**BASE_RESULT, "decision_intelligence": di}, DATE)
    assert "## 🔍 Decision Intelligence" in out
    assert "| Files governed by at least one memory | 8 |" in out
    assert "| HIGH confidence decisions | 3 |" in out
    assert "| MEDIUM confidence decisions | 2 |" in out
    assert "| LOW confidence decisions | 0 |" in out
    assert "| Active memories | 4 |" in out
    assert "| Superseded memories | 1 |" in out
    assert "Coverage Hotspots" not in out
    assert "Architecturally Broad Decisions" not in out


def test_hotspot_files():
    di = {
        "governed_file_count": 10,
        "confidence_distribution": {"HIGH": 5, "MEDIUM": 0, "LOW": 0},
        "status_distribution": {"Active": 5, "Superseded": 0},
        "hotspot_files": [
            {
                "file": "legacy/agents/cortexkeeper.py",
                "memory_count": 3,
                "memory_ids": ["004", "005", "006"],
                "risk_note": "High churn in retry logic.",
            }
        ],
        "broad_decisions": [],
        "coverage_recommendation": "",
    }
    out = render_issue_body({**BASE_RESULT, "decision_intelligence": di}, DATE)
    assert "### Coverage Hotspots" in out
    assert "legacy/agents/cortexkeeper.py" in out
    assert "3 memories" in out
    assert "#004" in out and "#005" in out and "#006" in out
    assert "High churn in retry logic." in out


def test_broad_decisions():
    di = {
        "governed_file_count": 12,
        "confidence_distribution": {"HIGH": 2, "MEDIUM": 3, "LOW": 0},
        "status_distribution": {"Active": 5, "Superseded": 0},
        "hotspot_files": [],
        "broad_decisions": [
            {
                "memory_id": "001",
                "file_count": 4,
                "files": ["a.py", "b.py", "c.py", "d.py"],
                "decision_summary": "All agents must use fixed retry intervals.",
            }
        ],
        "coverage_recommendation": "",
    }
    out = render_issue_body({**BASE_RESULT, "decision_intelligence": di}, DATE)
    assert "### Architecturally Broad Decisions" in out
    assert "Memory #001" in out
    assert "4 files" in out
    assert "All agents must use fixed retry intervals." in out
    assert "a.py" in out and "d.py" in out


def test_coverage_recommendation():
    di = {
        "governed_file_count": 5,
        "confidence_distribution": {"HIGH": 1, "MEDIUM": 4, "LOW": 0},
        "status_distribution": {"Active": 5, "Superseded": 0},
        "hotspot_files": [],
        "broad_decisions": [],
        "coverage_recommendation": "Add memory coverage for the webhook router — it has changed in 6 recent MRs with no governing decisions.",
    }
    out = render_issue_body({**BASE_RESULT, "decision_intelligence": di}, DATE)
    assert "### Coverage Recommendation" in out
    assert "webhook router" in out


def test_health_sections_intact_alongside_di():
    result = {
        **BASE_RESULT,
        "stale_memories": [
            {
                "memory_id": "002",
                "reason_stale": "Decision is 8 months old.",
                "urgency": "MEDIUM",
                "suggested_action": "Review with @alice.",
            }
        ],
        "review_memories": [],
        "decision_intelligence": {
            "governed_file_count": 3,
            "confidence_distribution": {"HIGH": 1, "MEDIUM": 2, "LOW": 0},
            "status_distribution": {"Active": 4, "Superseded": 1},
            "hotspot_files": [],
            "broad_decisions": [],
            "coverage_recommendation": "Expand coverage to auth layer.",
        },
    }
    out = render_issue_body(result, DATE)
    assert "Decision Intelligence" in out
    assert "Stale Memories" in out
    assert "Memory #002" in out
    assert "Decision is 8 months old." in out
    assert out.index("Decision Intelligence") < out.index("Stale Memories")
    assert "All Memories Healthy" not in out
    assert "Generated by CORTEX CORTEXCAST" in out


# ── standalone execution (python tests/test_cortexcast_rendering.py) ──────────

if __name__ == "__main__":
    failures = 0

    def check(name, condition, detail=""):
        global failures
        if condition:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))
            failures += 1

    print("=== Test 1: no decision_intelligence — existing sections intact ===")
    out1 = render_issue_body({**BASE_RESULT}, DATE)
    check("title rendered", f"CORTEX Health Report — {DATE}" in out1)
    check("summary table rendered", "| Total memories | 5 |" in out1)
    check("health summary rendered", "Memory is growing steadily." in out1)
    check("top recommendation rendered", "Review Memory #002 with @alice." in out1)
    check("no DI section when key absent", "Decision Intelligence" not in out1)
    check("all-healthy fallback shown", "All Memories Healthy" in out1)

    print()
    print("=== Test 2: confidence and status distribution ===")
    di2 = {
        "governed_file_count": 8,
        "confidence_distribution": {"HIGH": 3, "MEDIUM": 2, "LOW": 0},
        "status_distribution": {"Active": 4, "Superseded": 1},
        "hotspot_files": [],
        "broad_decisions": [],
        "coverage_recommendation": "",
    }
    out2 = render_issue_body({**BASE_RESULT, "decision_intelligence": di2}, DATE)
    check("DI section heading present", "## 🔍 Decision Intelligence" in out2)
    check("governed file count shown", "| Files governed by at least one memory | 8 |" in out2)
    check("HIGH confidence count", "| HIGH confidence decisions | 3 |" in out2)
    check("MEDIUM confidence count", "| MEDIUM confidence decisions | 2 |" in out2)
    check("LOW confidence count", "| LOW confidence decisions | 0 |" in out2)
    check("Active count", "| Active memories | 4 |" in out2)
    check("Superseded count", "| Superseded memories | 1 |" in out2)
    check("no hotspot section when empty", "Coverage Hotspots" not in out2)
    check("no broad section when empty", "Architecturally Broad Decisions" not in out2)

    print()
    print("=== Test 3: hotspot files ===")
    di3 = {
        "governed_file_count": 10,
        "confidence_distribution": {"HIGH": 5, "MEDIUM": 0, "LOW": 0},
        "status_distribution": {"Active": 5, "Superseded": 0},
        "hotspot_files": [
            {
                "file": "legacy/agents/cortexkeeper.py",
                "memory_count": 3,
                "memory_ids": ["004", "005", "006"],
                "risk_note": "High churn in retry logic.",
            }
        ],
        "broad_decisions": [],
        "coverage_recommendation": "",
    }
    out3 = render_issue_body({**BASE_RESULT, "decision_intelligence": di3}, DATE)
    check("hotspot section heading", "### Coverage Hotspots" in out3)
    check("hotspot file name", "legacy/agents/cortexkeeper.py" in out3)
    check("hotspot memory count", "3 memories" in out3)
    check("hotspot memory ids formatted", "#004" in out3 and "#005" in out3 and "#006" in out3)
    check("hotspot risk note", "High churn in retry logic." in out3)

    print()
    print("=== Test 4: broad decisions ===")
    di4 = {
        "governed_file_count": 12,
        "confidence_distribution": {"HIGH": 2, "MEDIUM": 3, "LOW": 0},
        "status_distribution": {"Active": 5, "Superseded": 0},
        "hotspot_files": [],
        "broad_decisions": [
            {
                "memory_id": "001",
                "file_count": 4,
                "files": ["a.py", "b.py", "c.py", "d.py"],
                "decision_summary": "All agents must use fixed retry intervals.",
            }
        ],
        "coverage_recommendation": "",
    }
    out4 = render_issue_body({**BASE_RESULT, "decision_intelligence": di4}, DATE)
    check("broad decisions heading", "### Architecturally Broad Decisions" in out4)
    check("broad memory id shown", "Memory #001" in out4)
    check("broad file count shown", "4 files" in out4)
    check("broad decision summary", "All agents must use fixed retry intervals." in out4)
    check("files listed", "a.py" in out4 and "d.py" in out4)

    print()
    print("=== Test 5: coverage recommendation ===")
    di5 = {
        "governed_file_count": 5,
        "confidence_distribution": {"HIGH": 1, "MEDIUM": 4, "LOW": 0},
        "status_distribution": {"Active": 5, "Superseded": 0},
        "hotspot_files": [],
        "broad_decisions": [],
        "coverage_recommendation": "Add memory coverage for the webhook router — it has changed in 6 recent MRs with no governing decisions.",
    }
    out5 = render_issue_body({**BASE_RESULT, "decision_intelligence": di5}, DATE)
    check("coverage recommendation heading", "### Coverage Recommendation" in out5)
    check("coverage recommendation text", "webhook router" in out5)

    print()
    print("=== Test 6: health sections intact alongside DI ===")
    result6 = {
        **BASE_RESULT,
        "stale_memories": [
            {
                "memory_id": "002",
                "reason_stale": "Decision is 8 months old.",
                "urgency": "MEDIUM",
                "suggested_action": "Review with @alice.",
            }
        ],
        "review_memories": [],
        "decision_intelligence": {
            "governed_file_count": 3,
            "confidence_distribution": {"HIGH": 1, "MEDIUM": 2, "LOW": 0},
            "status_distribution": {"Active": 4, "Superseded": 1},
            "hotspot_files": [],
            "broad_decisions": [],
            "coverage_recommendation": "Expand coverage to auth layer.",
        },
    }
    out6 = render_issue_body(result6, DATE)
    check("DI section present", "Decision Intelligence" in out6)
    check("stale memories section present", "Stale Memories" in out6)
    check("stale memory #002 present", "Memory #002" in out6)
    check("stale reason present", "Decision is 8 months old." in out6)
    check("DI appears before stale section", out6.index("Decision Intelligence") < out6.index("Stale Memories"))
    check("no all-healthy fallback when stale exists", "All Memories Healthy" not in out6)
    check("footer present", "Generated by CORTEX CORTEXCAST" in out6)

    print()
    if failures == 0:
        print("All tests PASSED")
        sys.exit(0)
    else:
        print(f"{failures} test(s) FAILED")
        sys.exit(1)
