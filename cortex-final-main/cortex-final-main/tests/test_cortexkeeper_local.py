"""
Local test for CORTEXKEEPER agent.
Tests the decision extraction pipeline without needing GitLab webhooks.
"""

import asyncio
import json
from datetime import datetime


async def test_cortexkeeper():
    """Test CORTEXKEEPER with a fake MR payload."""
    from legacy.agents.cortexkeeper import run_cortexkeeper
    
    # Simulate a merged MR with Decision #001
    fake_mr_payload = {
        "object_attributes": {
            "iid": 1,
            "id": 1,
            "title": "refactor: adopt fixed-interval retry strategy",
            "description": """
## Decision

Use fixed retry intervals instead of exponential backoff.

## Why

Exponential backoff can create uneven retry traffic under
high-concurrency situations.

Fixed intervals provide more predictable retry behaviour.

## Rejected alternative

Exponential backoff with jitter.

## Impact

This changes the retry behaviour used by the API authentication flow.

## Decision #001

Decision #001 — Fixed retry intervals are now the active retry strategy.
""",
            "state": "merged",
            "merge_commit_sha": "abc123def456",
            "action": "merge",
            "url": "https://gitlab.com/siemens-group4652530/cortex/-/merge_requests/1",
            "web_url": "https://gitlab.com/siemens-group4652530/cortex/-/merge_requests/1",
        },
        "user": {
            "username": "test-user",
            "name": "Test User",
            "id": 1,
        },
        "project": {
            "id": 84824921,
            "name": "cortex",
        },
    }
    
    print("\n" + "="*60)
    print("TEST: CORTEXKEEPER Local Test")
    print("="*60)
    print(f"Testing MR: {fake_mr_payload['object_attributes']['title']}")
    print(f"MR IID: {fake_mr_payload['object_attributes']['iid']}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*60 + "\n")
    
    try:
        print("[1/5] Calling run_cortexkeeper()...")
        await run_cortexkeeper(fake_mr_payload)
        print("✅ CORTEXKEEPER completed successfully\n")
        return True
    except Exception as e:
        print(f"❌ CORTEXKEEPER failed: {type(e).__name__}")
        print(f"Error: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_cortexkeeper())
    exit(0 if result else 1)
