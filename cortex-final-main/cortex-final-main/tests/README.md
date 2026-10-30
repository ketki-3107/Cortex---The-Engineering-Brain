# CORTEX Local Test Suite

Test all CORTEX agents **locally** without requiring GitLab webhooks, ngrok, or network calls.

## Quick Start

```powershell
cd "c:\My Workspace\Cortex"
.venv\Scripts\Activate.ps1

# Run all tests
python -m tests.run_all_tests

# Run individual tests
python -m tests.test_cortexkeeper_local
python -m tests.test_cortexcast_local
python -m tests.test_guardkeeper_local
python -m tests.test_specforge_local
```

## What Each Test Does

### 1. `test_cortexkeeper_local.py`
Tests **CORTEXKEEPER** — the decision extraction agent.
- **Trigger:** MR merge event
- **Input:** Fake MR payload with Decision #001
- **Expected:** Extracts decision and stores as memory
- **Tests:** 
  - Loading prompts ✓
  - Claude/Bedrock API call ✓
  - Decision parsing ✓
  - Wiki storage ✓

### 2. `test_cortexcast_local.py`
Tests **CORTEXCAST** — the health report generator.
- **Trigger:** Manual POST /cortexcast
- **Input:** All stored memories
- **Expected:** Generates health report identifying stale decisions
- **Tests:**
  - Memory retrieval ✓
  - Claude analysis ✓
  - Issue creation ✓

### 3. `test_guardkeeper_local.py`
Tests **GUARDKEEPER** — the security validator.
- **Trigger:** MR open event
- **Input:** Fake MR payload
- **Expected:** Checks MR against stored decisions, posts security check
- **Tests:**
  - Memory conflict detection ✓
  - Claude validation ✓
  - Comment posting ✓

### 4. `test_specforge_local.py`
Tests **SPECFORGE** — the spec generator.
- **Trigger:** Issue with @cortex mention
- **Input:** Fake issue payload
- **Expected:** Generates engineering spec from relevant memories
- **Tests:**
  - Keyword extraction ✓
  - Spec generation ✓
  - Comment posting ✓

## Troubleshooting

### Error: `ModuleNotFoundError: No module named 'legacy'`

Make sure you're in the Cortex workspace root and the venv is activated:

```powershell
cd "c:\My Workspace\Cortex"
.venv\Scripts\Activate.ps1
```

### Error: Missing botocore/boto3

Install AWS dependencies:

```powershell
pip install boto3 botocore
```

### Error: Missing credentials (GITLAB_TOKEN, AWS keys, etc.)

Check your `.env` file:

```powershell
cat legacy/.env
```

Make sure it has:
- `GITLAB_TOKEN` ✓
- `GITLAB_PROJECT_ID` ✓
- `AWS_ACCESS_KEY_ID` ✓
- `AWS_SECRET_ACCESS_KEY` ✓
- `CLAUDE_PROVIDER=bedrock` ✓

### Error: `Invalid Credential...` from AWS

Your AWS credentials in `.env` may be expired or invalid. Update them:

```powershell
# Get new credentials from AWS Console
# Then update legacy/.env and try again
```

## Next Steps After Tests Pass

1. ✅ All 4 tests pass locally
2. Start CORTEX server: `python -m legacy.main`
3. Start ngrok tunnel: `ngrok http 8000`
4. Configure GitLab webhook with ngrok URL
5. Merge a real MR → watch webhook trigger in server logs
6. Verify memory created in GitLab wiki

## Development Workflow

**During development:**

```
1. Make code change
2. Run: python -m tests.run_all_tests
3. Check logs for failures
4. Fix and repeat
5. Only then test with real GitLab
```

This is much faster than creating test MRs every time! 🚀

## Adding New Tests

To add a test for a new agent:

1. Create `test_<agent>_local.py` in this directory
2. Import the agent function
3. Create a fake payload (copy structure from existing tests)
4. Call the async function
5. Handle exceptions and report status
6. Add to `run_all_tests.py`

Example:

```python
async def test_new_agent():
    from legacy.agents.new_agent import run_new_agent
    
    fake_payload = {...}
    
    try:
        await run_new_agent(fake_payload)
        print("✅ NEW_AGENT completed successfully\n")
        return True
    except Exception as e:
        print(f"❌ NEW_AGENT failed: {e}\n")
        return False
```
