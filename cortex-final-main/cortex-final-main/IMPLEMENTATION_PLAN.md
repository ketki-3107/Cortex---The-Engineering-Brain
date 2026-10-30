# CORTEX — Implementation Plan: Decision Intelligence + Org Memory

**File to change:** `flows/flow.yml` only  
**Implementation type:** Prompt engineering — no new infrastructure, no code changes  
**Scope:** Features 1 and 2 from the PNA, with notes on Features 3 and 4 (ChatGPT additions)

---

## What We're Building and Why

| Feature | Value |
|---|---|
| Engineering Decision Intelligence | Captures WHY behind decisions (trade-offs, alternatives, category) and detects conflicts/duplicates automatically |
| Cross-Project Org Memory | Lets one project's agreed standards govern other projects — a shared layer above project memories |
| Decision Replay (F3, lower priority) | Shows the full history of how a decision evolved, using data CORTEX already collects |
| Expertise Discovery (F4, lowest priority) | Derives who knows what from MR authorship + decision authorship — evidence-based, no guessing |

Features 1 and 2 are the demo centrepiece. Features 3 and 4 are extensions that reuse existing data and should only be built after 1 and 2 are stable.

---

## Current State (what exists in `flows/flow.yml`)

| Component | Type | Status |
|---|---|---|
| triage_router | AgentComponent | Routes to 7 agents using classification rules |
| specforge_agent | AgentComponent | Pre-mortem + spec on issues |
| guardkeeper_agent | AgentComponent | 5-layer conflict/security check on open MRs |
| reply_handler_agent | AgentComponent | Processes `cortex:` reply commands |
| cortexkeeper_agent | AgentComponent | Decision extraction on merged MRs |
| cortexcast_agent | AgentComponent | Health audit |
| onboarding_agent | AgentComponent | New-member briefing |
| commitkeeper_agent | AgentComponent | Commit ledger |

Memory lives in: GitLab wiki (`CORTEX-INDEX`, `CORTEX-MEMORY-{id}`)  
Writing target: "CORTEX Memory Bank" issue

---

## Step 1 — Extend the Memory Schema (in CORTEXKEEPER prompt)

**Where:** `cortexkeeper_prompt` system message, after the existing memory format description.

**What to add to the format documentation inside the prompt:**

```
Extended memory fields (additive — existing memories without these remain valid):

Alternatives considered: [comma-separated approaches evaluated but not chosen]
Trade offs:              [Gain: X. Lose: Y.]
Category:                [ARCHITECTURE | SECURITY | PERFORMANCE | TOOLING | PROCESS | DATA | INFRA]
Supersedes:              [CORTEX Memory NNN, or N/A]
Confidence reason:       [one sentence explaining HIGH/MEDIUM/LOW]
Review by:               [ISO-8601 date, or NONE]
Scope:                   [PROJECT | ORGANISATION]
```

**Rules to add for when to populate these fields:**

- `Alternatives considered` — scan discussion for "we considered X but", "we ruled out Y because", "X was proposed but rejected"
- `Trade offs` — scan for "the downside is", "this means we lose", "the benefit is", "the cost is"
- `Category` — infer from files touched and discussion topic
- `Review by` — SECURITY decisions: 6 months from merge date; ARCHITECTURE: 12 months; TOOLING/PROCESS: 18 months; others: NONE
- `Scope` — PROJECT by default; promote to ORGANISATION if the decision involves an auth pattern, API convention, security standard, or cross-project concern
- `Supersedes` — if this decision explicitly overrides a prior one (detected from "instead of", "replacing", `cortex: intentional` flow), link the old memory ID

**Conflict + duplicate detection (add to PHASE 0):**

```
Before creating any new memory:
1. Fetch CORTEX-INDEX.
2. For each relevant existing memory, fetch the full page.
3. Semantic equivalence check: does the new decision implement the same constraint as an existing one?
   - If YES and content matches: do NOT create a duplicate. Post a note linking to the existing memory instead.
   - If YES and content conflicts: create the new memory with Status: Conflicting, note the conflicting memory ID in the comment.
4. Log in the MR summary under a "Decision Intelligence" section:
   - Decisions that supersede old ones (with links)
   - Conflicts detected
   - Duplicates merged/linked
   - Category breakdown table
```

**Validation test for Step 1:**  
Merge an MR with discussion that contains trade-off language ("the downside of this approach is...") and verify CORTEXKEEPER's memory entry includes `Alternatives considered`, `Trade offs`, `Category`, `Review by`, and `Scope` fields.

---

## Step 2 — Enhance GUARDKEEPER (Layer 0 + Layer 1 improvements)

**Where:** `guardkeeper_prompt` system message.

### Add Layer 0 — Organisation Standards Check (prepend before existing Layer 1)

```
LAYER 0 — ORGANISATION STANDARDS CHECK (run first):
1. Read CORTEX-ORG-INDEX wiki page (slug: "CORTEX-ORG-INDEX"). If it does not exist yet, skip Layer 0 silently.
2. Find org memories whose `Governs files` overlaps the changed files, OR whose Category is SECURITY or ARCHITECTURE.
3. If org memories found: display them FIRST in the comment under the header "🏢 ORGANISATION STANDARDS" with higher visual prominence than local decisions.
4. Org standard conflicts are always HIGH severity — they represent cross-team agreements.

Output format for org standard violations:
🏢 ORGANISATION STANDARD
CORTEX-ORG-MEMORY-{id}: {decision title}
🚨 HIGH SEVERITY — This MR conflicts with an organisation-wide standard.
```

### Layer 1 enhancements (add to existing Layer 1 instruction)

```
Enhanced Layer 1 additions:
- Category-aware severity: any conflict with a memory whose Category is SECURITY → always HIGH severity, regardless of other factors.
- Duplicate detection: if the MR introduces a pattern that is semantically equivalent to an existing memory → post "This pattern was already decided in CORTEX Memory {N} — is this an extension or override?"
- Trade-off regression: if a memory has a `Trade offs` field documenting what was sacrificed, and the MR appears to reclaim what was sacrificed (reversing the trade-off without justification) → flag it explicitly.
- Supersedes chain: if memory A was superseded by memory B (check Supersedes field), only memory B governs. Do not double-flag from memory A.
```

**Validation test for Step 2:**  
Open an MR that contradicts an existing memory's stated trade-off. Verify GUARDKEEPER flags a trade-off regression with the specific memory cited.

---

## Step 3 — Enhance CORTEXCAST (Decision Intelligence section)

**Where:** `cortexcast_prompt` system message, in the CREATE ISSUE block.

**Add a new section after the existing Decision Health table:**

```
DECISION INTELLIGENCE SUMMARY section:
- Table: decisions grouped by Category (ARCHITECTURE | SECURITY | PERFORMANCE | TOOLING | PROCESS | DATA | INFRA) with counts
- Conflicting decisions requiring human resolution (list memories with Status: Conflicting, with links)
- Decision evolution chains (supersedes relationships: Memory A → superseded by → Memory B)
- Decisions past their Review by date (staleness alerts with original review date and current date)
- Completeness gaps: memories missing Trade offs field, memories missing Alternatives considered field
```

**Add an Organisation Coverage section (appears even before org memories exist, so future-proof):**

```
ORGANISATION COVERAGE section:
- Count of CORTEX-ORG-MEMORY entries that govern files in this project (read CORTEX-ORG-INDEX; if none exists, state "No organisation memories yet")
- Count of local decisions with Scope: ORGANISATION that have not yet been promoted (candidates for promotion)
- Count of local decisions successfully promoted to org level
```

**Validation test for Step 3:**  
Trigger CORTEXCAST and verify the report contains a category breakdown table and lists any memories past their `Review by` date.

---

## Step 4 — Enhance ONBOARDING (Org Standards section)

**Where:** `onboarding_prompt` system message.

**Add a new first section before all existing output:**

```
New first section in the onboarding issue:

ORGANISATION STANDARDS (applies across all projects)
1. Read CORTEX-ORG-INDEX wiki page. If it does not exist, write: "No organisation-wide standards have been defined yet."
2. If it exists: fetch each CORTEX-ORG-MEMORY-{id} page and display them grouped by Category.
3. Show: Decision | Category | Source project | Promoted by | Governs files

Then continue with the existing PROJECT DECISIONS sections.
```

**Rationale:** New engineers must know what the whole org agreed on before learning project-specific decisions. This ordering is intentional.

**Validation test for Step 4:**  
After Step 5 (ORGKEEPER) creates at least one org memory, request onboarding briefing and verify "ORGANISATION STANDARDS" appears as the first section.

---

## Step 5 — Add ORGKEEPER Agent (new component + prompt + router rule)

This is the largest addition: a new 9th agent.

### 5a. New component block (add after commitkeeper_agent in the `components:` list)

```yaml
# ── 9. ORGKEEPER AGENT (org memory promotion) ─────────────────────
- name: "orgkeeper_agent"
  type: AgentComponent
  prompt_id: "orgkeeper_prompt"
  inputs:
    - from: "context:goal"
      as: "user_goal"
    - from: "context:project_id"
      as: "project_id"
  toolset:
    - "get_merge_request"
    - "list_merge_request_diffs"
    - "list_all_merge_request_notes"
    - "build_review_merge_request_context"
    - "create_merge_request_note"
    - "update_merge_request"
    - "get_issue"
    - "list_issue_notes"
    - "create_issue_note"
    - "create_issue"
    - "update_issue"
    - "get_wiki_page"
    - "gitlab_wiki_blob_search"
    - "gitlab_api_get"
    - "gitlab_issue_search"
    - "gitlab_note_search"
    - "gitlab_merge_request_search"
  ui_log_events:
    - "on_agent_final_answer"
    - "on_tool_execution_success"
    - "on_tool_execution_failed"
```

### 5b. New ORGKEEPER prompt (add after commitkeeper_prompt in the `prompts:` list)

```
You are CORTEX's ORGKEEPER agent — organisation memory curator. Powered by Anthropic Claude.

PURPOSE: Promote a project-level decision to the organisation memory layer so all projects sharing this hub inherit it as a standard.

TRIGGER: A developer has posted `cortex: promote-to-org` on an MR or issue note, or the user_goal mentions "promote decision", "organisation standard", "org memory", "share this decision".

ORG MEMORY STORAGE:
- Index: CORTEX-ORG-INDEX wiki page (same format as CORTEX-INDEX)
- Pages: CORTEX-ORG-MEMORY-{NNN} wiki pages
- Write target: "CORTEX Organisation Memory Bank" issue (label: cortex-org-memory). Find or create it.

ORG MEMORY FORMAT (same as regular memory, plus):
Source project: {current project path}
Promoted by: @{username who posted the promote command}

STEPS:
1. Find the memory being promoted: read the context note to identify which CORTEX Memory is referenced, or infer from the current MR/issue.
2. Fetch the full memory content from the wiki.
3. Read CORTEX-ORG-INDEX. Fetch any org memories with overlapping Governs files or Category.
4. Conflict/duplicate check:
   - If a semantically equivalent org memory exists: do NOT create a duplicate. Notify the user and link to the existing org memory.
   - If a conflicting org memory exists: flag it and require human resolution before promoting.
5. If clean:
   a. Determine next org memory number (read CORTEX-ORG-INDEX for highest existing number).
   b. Write org memory to "CORTEX Organisation Memory Bank" issue with Source project and Promoted by fields.
   c. Update CORTEX-ORG-INDEX with the new entry.
   d. Update the original project memory: add `Scope: ORGANISATION` and link to the new CORTEX-ORG-MEMORY-{NNN}.
6. Post confirmation on the MR/issue:
   Decision promoted to Organisation Memory as CORTEX-ORG-MEMORY-{NNN}.
   Source project: {project_path}
   Promoted by: @{username}
   All projects sharing this hub will now inherit this standard.

TEACH THE COMMAND: Include in your response a one-line reminder of the promote syntax:
   To promote a future decision, comment: `cortex: promote-to-org` on any MR or issue.

CRITICAL: Never use # before numbers for memory references. Use CORTEX-001, CORTEX-ORG-MEMORY-001, or `CORTEX Memory 001` instead. Sign "— CORTEX". Footer: "Powered by Anthropic Claude."
```

### 5c. New router rule (add to triage_router_prompt classification rules)

Insert as priority 1.5 — between the existing rule 1 (REPLY_HANDLER) and rule 2 (COMMITKEEPER). Renumber existing rules 2–7 to 3–8:

```
2. ORGKEEPER — {{user_goal}} or a recent MR/issue note contains `cortex: promote-to-org`, or {{user_goal}} mentions "organisation standard", "promote decision", "org memory", "share this decision". Route to: orgkeeper_agent.
```

Update the valid agent name list in the router output format to include `orgkeeper_agent`.

### 5d. New router entry (add to `routers:` list)

```yaml
- from: "triage_router"
  to: "orgkeeper_agent"
- from: "orgkeeper_agent"
  to: "end"
```

**Validation test for Step 5:**  
Comment `cortex: promote-to-org` on an MR that has a CORTEX memory. Verify ORGKEEPER creates `CORTEX-ORG-MEMORY-001` wiki page, updates `CORTEX-ORG-INDEX`, and posts a confirmation comment.

---

## Step 6 — Decision Replay (Feature 3, lower priority)

**Where:** CORTEXCAST prompt and/or a new `cortexask_prompt` (CORTEX Ask already exists as part of the triage flow via the general agent path).

**Approach:** No new storage. CORTEX already has all the data needed:
- `Supersedes` chain links memories chronologically
- `Source MR` links each memory to its origin
- `Status: Conflicting` / `Status: Superseded` fields mark evolution points
- GUARDKEEPER's conflict comments are already stored on MRs

**What to add to the CORTEXCAST prompt:**

```
DECISION REPLAY section (only if user requests it — keyword: "replay", "history of", "evolution of"):
1. Take the decision topic or memory ID from the user_goal.
2. Fetch the current memory.
3. Walk the Supersedes chain backwards (fetch each superseded memory).
4. Fetch each source MR to find when GUARDKEEPER detected the conflict and what the developer replied.
5. Render a chronological chain:
   Memory A created (MR !{N}, {date}) → Conflict detected in MR !{M} → Developer approved override → Memory B active (MR !{M}, {date})
```

This adds zero storage and zero new agents — it is a read-only reconstruction from existing data.

---

## Step 7 — Expertise Discovery (Feature 4, lowest priority)

**Where:** Add to CORTEXCAST as an optional section, or to CORTEX Ask routing.

**Approach:** Evidence-based only. Use:
- MR authors + reviewers from `list_all_merge_request_notes`
- `Decided by` field in memories
- Memory `Category` fields
- No scores without evidence

**What to add to CORTEXCAST prompt (optional section):**

```
EXPERTISE MAP section (only if user requests it — keyword: "expertise", "who knows", "who decided"):
For each person who appears as Decided by across memories:
- Count decisions by Category
- List memory IDs they decided
- List MRs they authored where memories were created
Output: Person | Categories | Decision count | Key memory IDs
Do NOT state someone is an "expert" — state what their documented contributions are.
```

---

## Implementation Order

| Step | What | Validation |
|---|---|---|
| 1 | Extend memory schema + CORTEXKEEPER extraction + duplicate detection | Merge an MR with trade-off discussion |
| 2 | GUARDKEEPER Layer 0 (org) + Layer 1 enhancements | Open MR conflicting with existing decision's trade-off |
| 3 | CORTEXCAST Decision Intelligence + Org Coverage sections | Trigger CORTEXCAST |
| 4 | ONBOARDING Org Standards section | Request onboarding briefing |
| 5 | ORGKEEPER agent + component + router rule | Post `cortex: promote-to-org` |
| 6 | Decision Replay in CORTEXCAST (after 1–5 stable) | Ask for history of a specific decision |
| 7 | Expertise Discovery in CORTEXCAST (last) | Ask who has expertise in a category |

Steps 1–5 are the demo. Steps 6–7 build on the data that 1–5 accumulate.

---

## Demo Flow (Final Validation)

```
1. Merge MR with retry strategy decision
   → CORTEXKEEPER posts memory with Trade offs, Category: PERFORMANCE, Alternatives considered
   
2. Open new MR that switches to exponential backoff
   → GUARDKEEPER Layer 1 detects trade-off regression
   → Comment shows original decision's "Gain: predictable traffic. Lose: adaptive timing"
   
3. Developer approves the override with `cortex: intentional — benchmarking shows jitter is safe`
   → REPLY_HANDLER creates new memory, Supersedes: CORTEX Memory 001
   
4. Post `cortex: promote-to-org` on the new memory
   → ORGKEEPER creates CORTEX-ORG-MEMORY-001
   → CORTEX-ORG-INDEX updated
   
5. Open MR in second project touching same retry files
   → GUARDKEEPER Layer 0 shows 🏢 ORGANISATION STANDARD first
   → HIGH severity conflict
   
6. Trigger CORTEXCAST
   → Decision Intelligence Summary: category table, 1 superseded chain, Org Coverage: 1 org memory
   
7. Request onboarding briefing
   → ORGANISATION STANDARDS section appears before project decisions
   
8. Ask CORTEX: "Show me the history of the retry strategy decision"
   → Decision replay chain rendered from Supersedes chain + source MRs
```

---

## Risks and Open Questions

| Risk | Mitigation |
|---|---|
| CORTEX-ORG-INDEX does not exist on first run | All agents that read it must handle the case gracefully (skip silently or state "No org memories yet") |
| Duplicate detection is semantic — LLM may miss equivalences | Add explicit instructions to check file paths as a hard signal before semantic comparison |
| `Supersedes` chain creates circular references if populated incorrectly | CORTEXKEEPER should only set Supersedes when a `cortex: intentional` override is confirmed, not inferred |
| Org memory promotion without a second project to test | Document test as: simulate by checking that GUARDKEEPER Layer 0 fires within the same project on a new MR |
| Features 3 and 4 depend on Features 1 and 2 data being present | Do not build 3 and 4 until at least 3 real MRs have gone through the enhanced CORTEXKEEPER |

---

## Summary: What Changes in `flows/flow.yml`

| Section | Change |
|---|---|
| `cortexkeeper_prompt` system | Add 7 new schema fields, extraction rules, conflict/duplicate detection, Decision Intelligence MR summary section |
| `guardkeeper_prompt` system | Prepend Layer 0 (org standards check), enhance Layer 1 with category-aware severity + trade-off regression + supersedes chain |
| `cortexcast_prompt` system | Add Decision Intelligence Summary section + Org Coverage section |
| `onboarding_prompt` system | Add Org Standards section as the new first section |
| `triage_router_prompt` system | Add ORGKEEPER classification rule at priority 2 (renumber old 2–7 to 3–8), add orgkeeper_agent to valid routes list |
| `components:` block | Add orgkeeper_agent component (identical toolset to other agents) |
| `prompts:` block | Add orgkeeper_prompt |
| `routers:` block | Add `triage_router → orgkeeper_agent` and `orgkeeper_agent → end` |
