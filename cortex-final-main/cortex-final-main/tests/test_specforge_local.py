"""
Local test for SPECFORGE agent.
Tests spec generation from issue mentions.
"""

import asyncio
from datetime import datetime


async def test_specforge():
    """Test SPECFORGE with a fake issue payload containing @cortex mention."""
    from legacy.agents.specforge import run_specforge
    
    # Simulate an issue being created with @cortex mention
    fake_issue_payload = {
        "object_attributes": {
            "id": 1,
            "iid": 1,
            "title": "Implement OAuth2 authentication",
            "description": """
We need to implement OAuth2 authentication for our API.

@cortex please generate a spec for this feature.

## Requirements
- Support Google and GitHub OAuth providers
- Store tokens securely
- Rate limiting per user
""",
            "state": "opened",
            "action": "open",
            "url": "https://gitlab.com/siemens-group4652530/cortex/-/issues/1",
            "web_url": "https://gitlab.com/siemens-group4652530/cortex/-/issues/1",
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
    print("TEST: SPECFORGE Local Test")
    print("="*60)
    print(f"Testing Issue: {fake_issue_payload['object_attributes']['title']}")
    print(f"Issue IID: {fake_issue_payload['object_attributes']['iid']}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*60 + "\n")
    
    try:
        print("[1/3] Calling run_specforge()...")
        await run_specforge(fake_issue_payload)
        print("✅ SPECFORGE completed successfully\n")
        return True
    except Exception as e:
        print(f"❌ SPECFORGE failed: {type(e).__name__}")
        print(f"Error: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_specforge())
    exit(0 if result else 1)
