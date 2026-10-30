"""
Local test for GUARDKEEPER agent.
Tests security validation against stored decisions.
"""

import asyncio
from datetime import datetime


async def test_guardkeeper():
    """Test GUARDKEEPER with a fake MR open payload."""
    from legacy.agents.guardkeeper import run_guardkeeper
    
    # Simulate an MR being opened (action: open)
    fake_mr_payload = {
        "object_attributes": {
            "iid": 2,
            "id": 2,
            "title": "feat: add new authentication flow",
            "description": "Adding OAuth2 support",
            "state": "opened",
            "action": "open",
            "url": "https://gitlab.com/siemens-group4652530/cortex/-/merge_requests/2",
            "web_url": "https://gitlab.com/siemens-group4652530/cortex/-/merge_requests/2",
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
    print("TEST: GUARDKEEPER Local Test")
    print("="*60)
    print(f"Testing MR: {fake_mr_payload['object_attributes']['title']}")
    print(f"MR IID: {fake_mr_payload['object_attributes']['iid']}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*60 + "\n")
    
    try:
        print("[1/3] Calling run_guardkeeper()...")
        await run_guardkeeper(fake_mr_payload, reply_type=None)
        print("✅ GUARDKEEPER completed successfully\n")
        return True
    except Exception as e:
        print(f"❌ GUARDKEEPER failed: {type(e).__name__}")
        print(f"Error: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_guardkeeper())
    exit(0 if result else 1)
