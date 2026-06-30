#!/usr/bin/env python3
"""
Debug multiagent flow
"""
import asyncio
import json
import os
import sys
import logging

# Add current directory to Python path
sys.path.insert(0, '.')

from common import setup_logging
from orchestrator import run_pipeline

# Setup logging
setup_logging("debug_multiagent")
log = logging.getLogger("debug_multiagent")

async def debug_simple_task():
    """Test a simple task to debug the flow"""

    task = "什么是Python？"

    print("=== Testing MultiAgent Flow ===")
    print(f"Task: {task}")
    print()

    try:
        # Test with reduced timeout to see if we can get partial results
        result = await run_pipeline(
            task,
            mode='parallel',
            timeout_s=30,  # Reduced timeout
        )

        print("=== Result ===")
        print(f"Success: {result.get('success', False)}")
        print(f"Final Answer: {result.get('final_answer', '')[:500]}...")
        print()

        # Print individual results
        print("=== Individual Platform Results ===")
        if 'results' in result:
            for platform in ['chatgpt', 'gemini', 'kimi']:
                platform_result = None
                for r in result['results']:
                    if r['platform'] == platform:
                        platform_result = r
                        break

                if platform_result:
                    status = "✅" if platform_result.get('success') else "❌"
                    print(f"{platform}: {status} ({platform_result.get('length', 0)} chars)")
                    if platform_result.get('timeout'):
                        print("  [TIMEOUT]")
                    if platform_result.get('error'):
                        print(f"  Error: {platform_result['error']}")
                    print(f"  Response preview: {platform_result['response'][:200]}...")
                else:
                    print(f"{platform}: No result")
                print()

        # Print adjudication
        print("=== Adjudication ===")
        if 'phase4_result' in result:
            print(f"Phase 4 result: {result['phase4_result'][:200]}...")
        else:
            print("No Phase 4 result")

    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

async def debug_phase4_only():
    """Test just the phase4 adjudication"""

    # Mock matrix data
    matrix = """
[ChatGPT]
Python is a high-level programming language...

[Gemini]
Python is an interpreted language...

[Kimi]
Python is a general-purpose language...
"""

    task_core = "什么是Python？"

    print("=== Testing Phase 4 Only ===")
    from orchestrator import phase4_adjudicate

    try:
        result = await phase4_adjudicate(matrix, task_core)
        print(f"Phase 4 Result: {result}")
    except Exception as e:
        print(f"Exception in Phase 4: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Test both
    print("1. Testing full pipeline...")
    asyncio.run(debug_simple_task())
    print("\n" + "="*50 + "\n")

    print("2. Testing Phase 4 only...")
    asyncio.run(debug_phase4_only())