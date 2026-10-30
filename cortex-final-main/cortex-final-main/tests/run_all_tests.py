"""
Master test runner for all CORTEX agents.
Runs all local tests in sequence and reports results.

Usage:
    python -m tests.run_all_tests
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path


async def run_all_tests():
    """Run all agent tests sequentially."""
    
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*20 + "CORTEX Agent Test Suite" + " "*25 + "║")
    print("╚" + "="*68 + "╝")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    results = {}
    
    # Test 1: CORTEXKEEPER
    print("\n[TEST 1/4] CORTEXKEEPER")
    print("-" * 70)
    try:
        from tests.test_cortexkeeper_local import test_cortexkeeper
        result = await test_cortexkeeper()
        results["cortexkeeper"] = result
        if not result:
            print("⚠️  CORTEXKEEPER has errors but may be recoverable")
    except Exception as e:
        print(f"❌ Failed to import/run cortexkeeper test: {e}")
        results["cortexkeeper"] = False
    
    # Test 2: CORTEXCAST
    print("\n[TEST 2/4] CORTEXCAST")
    print("-" * 70)
    try:
        from tests.test_cortexcast_local import test_cortexcast
        result = await test_cortexcast()
        results["cortexcast"] = result
        if not result:
            print("⚠️  CORTEXCAST has errors but may be recoverable")
    except Exception as e:
        print(f"❌ Failed to import/run cortexcast test: {e}")
        results["cortexcast"] = False
    
    # Test 3: GUARDKEEPER
    print("\n[TEST 3/4] GUARDKEEPER")
    print("-" * 70)
    try:
        from tests.test_guardkeeper_local import test_guardkeeper
        result = await test_guardkeeper()
        results["guardkeeper"] = result
        if not result:
            print("⚠️  GUARDKEEPER has errors but may be recoverable")
    except Exception as e:
        print(f"❌ Failed to import/run guardkeeper test: {e}")
        results["guardkeeper"] = False
    
    # Test 4: SPECFORGE
    print("\n[TEST 4/4] SPECFORGE")
    print("-" * 70)
    try:
        from tests.test_specforge_local import test_specforge
        result = await test_specforge()
        results["specforge"] = result
        if not result:
            print("⚠️  SPECFORGE has errors but may be recoverable")
    except Exception as e:
        print(f"❌ Failed to import/run specforge test: {e}")
        results["specforge"] = False
    
    # Summary
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*25 + "Test Results Summary" + " "*23 + "║")
    print("╠" + "="*68 + "╣")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for agent, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"║  {agent.upper():15s} ... {status:12s}" + " "*38 + "║")
    
    print("╠" + "="*68 + "╣")
    print(f"║  Total: {passed}/{total} passed" + " "*55 + "║")
    print("╚" + "="*68 + "╝")
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
