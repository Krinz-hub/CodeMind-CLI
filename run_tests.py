#!/usr/bin/env python3
"""Hermetic offline test runner for CodeMind CLI."""

import sys
import unittest
from pathlib import Path

# Add src and current directory to sys.path
root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir / "src"))
sys.path.insert(0, str(root_dir))


def main() -> int:
    print("=" * 60)
    print("▟●▙ CodeMind CLI - Hermetic Offline Test Suite")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(root_dir / "tests"), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"✓ All {result.testsRun} tests passed successfully!")
        print("=" * 60)
        return 0
    else:
        print(f"✗ Test run failed! Failures: {len(result.failures)}, Errors: {len(result.errors)}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
