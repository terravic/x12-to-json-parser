"""
Master Test Runner for X12 Parser & Clinical C-CDA Integration Suite.

Discovers and executes all unit, integration, and manifest test suites.
"""

import sys
import unittest
import os

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def run_suite():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Discover tests in tests directory
    tests_dir = os.path.join(PROJECT_ROOT, "tests")
    discovered = loader.discover(start_dir=tests_dir, pattern="test_*.py")
    suite.addTests(discovered)

    print("=" * 70)
    print("RUNNING X12 HEALTHCARE PARSER & C-CDA TEST SUITE")
    print("=" * 70)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print("TEST SUITE EXECUTION SUMMARY")
    print("=" * 70)
    print(f"Total Tests Executed: {result.testsRun}")
    print(f"Passed:               {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures:             {len(result.failures)}")
    print(f"Errors:               {len(result.errors)}")
    print("=" * 70)

    if not result.wasSuccessful():
        sys.exit(1)
    else:
        print(">> ALL TEST CASES PASSED SUCCESSFULLY (100% SUCCESS RATE) <<\n")
        sys.exit(0)


if __name__ == "__main__":
    run_suite()
