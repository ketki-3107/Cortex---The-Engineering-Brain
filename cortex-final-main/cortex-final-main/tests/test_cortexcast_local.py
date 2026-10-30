"""
Local test for CORTEXCAST agent.
Tests the health report generation without needing manual POST triggers.
"""

import asyncio
from datetime import datetime


async def test_cortexcast():
    """Test CORTEXCAST health report generation."""
    from legacy.agents.cortexcast import run_cortexcast
    
    print("\n" + "="*60)
    print("TEST: CORTEXCAST Local Test")
    print("="*60)
    print("Testing health report generation")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*60 + "\n")
    
    try:
        print("[1/3] Calling run_cortexcast()...")
        await run_cortexcast()
        print("✅ CORTEXCAST completed successfully\n")
        return True
    except Exception as e:
        print(f"❌ CORTEXCAST failed: {type(e).__name__}")
        print(f"Error: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_cortexcast())
    exit(0 if result else 1)
