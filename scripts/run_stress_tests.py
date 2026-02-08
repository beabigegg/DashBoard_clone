#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stress Test Runner for MES Dashboard

Runs comprehensive stress tests including:
- Backend API load tests
- Frontend browser stress tests

Usage:
    python scripts/run_stress_tests.py [options]

Options:
    --backend-only      Run only backend API tests
    --frontend-only     Run only frontend Playwright tests
    --quick             Quick test with minimal load (good for CI)
    --heavy             Heavy load test (10x normal)
    --url URL           Target URL (default: http://127.0.0.1:5000)
    --report FILE       Save report to file
"""

import argparse
import subprocess
import sys
import os
import time
from datetime import datetime


def run_backend_tests(url: str, config: dict) -> dict:
    """Run backend API stress tests."""
    env = os.environ.copy()
    env['STRESS_TEST_URL'] = url
    env['STRESS_CONCURRENT_USERS'] = str(config.get('concurrent_users', 10))
    env['STRESS_REQUESTS_PER_USER'] = str(config.get('requests_per_user', 20))
    env['STRESS_TIMEOUT'] = str(config.get('timeout', 30))

    print("\n" + "=" * 60)
    print("Running Backend API Load Tests")
    print("=" * 60)
    print(f"  URL: {url}")
    print(f"  Concurrent Users: {config.get('concurrent_users', 10)}")
    print(f"  Requests/User: {config.get('requests_per_user', 20)}")
    print()

    start_time = time.time()
    result = subprocess.run(
        ['python', '-m', 'pytest', 'tests/stress/test_api_load.py', '-v', '-s', '--tb=short'],
        env=env,
        capture_output=False,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    duration = time.time() - start_time

    return {
        'name': 'Backend API Load Tests',
        'passed': result.returncode == 0,
        'duration': duration,
        'returncode': result.returncode
    }


def run_frontend_tests(url: str, config: dict) -> dict:
    """Run frontend Playwright stress tests."""
    env = os.environ.copy()
    env['STRESS_TEST_URL'] = url

    print("\n" + "=" * 60)
    print("Running Frontend Playwright Stress Tests")
    print("=" * 60)
    print(f"  URL: {url}")
    print()

    start_time = time.time()
    result = subprocess.run(
        ['python', '-m', 'pytest', 'tests/stress/test_frontend_stress.py', '-v', '-s', '--tb=short'],
        env=env,
        capture_output=False,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    duration = time.time() - start_time

    return {
        'name': 'Frontend Playwright Stress Tests',
        'passed': result.returncode == 0,
        'duration': duration,
        'returncode': result.returncode
    }


def generate_report(results: list, url: str, config: dict) -> str:
    """Generate a text report of stress test results."""
    report_lines = [
        "=" * 60,
        "MES Dashboard Stress Test Report",
        "=" * 60,
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Target URL: {url}",
        f"Configuration: {config}",
        "",
        "-" * 60,
        "Test Results:",
        "-" * 60,
    ]

    total_duration = 0
    passed_count = 0

    for result in results:
        status = "PASSED" if result['passed'] else "FAILED"
        report_lines.append(f"  {result['name']}: {status}")
        report_lines.append(f"    Duration: {result['duration']:.2f}s")
        total_duration += result['duration']
        if result['passed']:
            passed_count += 1

    report_lines.extend([
        "",
        "-" * 60,
        "Summary:",
        "-" * 60,
        f"  Total Tests: {len(results)}",
        f"  Passed: {passed_count}",
        f"  Failed: {len(results) - passed_count}",
        f"  Total Duration: {total_duration:.2f}s",
        "=" * 60,
    ])

    return "\n".join(report_lines)


def main():
    parser = argparse.ArgumentParser(description='Run MES Dashboard stress tests')
    parser.add_argument('--backend-only', action='store_true', help='Run only backend tests')
    parser.add_argument('--frontend-only', action='store_true', help='Run only frontend tests')
    parser.add_argument('--quick', action='store_true', help='Quick test with minimal load')
    parser.add_argument('--heavy', action='store_true', help='Heavy load test')
    parser.add_argument('--url', default='http://127.0.0.1:5000', help='Target URL')
    parser.add_argument('--report', help='Save report to file')

    args = parser.parse_args()

    # Configure load levels
    if args.quick:
        config = {
            'concurrent_users': 3,
            'requests_per_user': 5,
            'timeout': 30
        }
    elif args.heavy:
        config = {
            'concurrent_users': 50,
            'requests_per_user': 50,
            'timeout': 60
        }
    else:
        config = {
            'concurrent_users': 10,
            'requests_per_user': 20,
            'timeout': 30
        }

    print("\n" + "=" * 60)
    print("MES Dashboard Stress Test Suite")
    print("=" * 60)
    print(f"Target: {args.url}")
    print(f"Mode: {'Quick' if args.quick else 'Heavy' if args.heavy else 'Normal'}")
    print()

    results = []

    # Run tests based on flags
    if not args.frontend_only:
        results.append(run_backend_tests(args.url, config))

    if not args.backend_only:
        results.append(run_frontend_tests(args.url, config))

    # Generate report
    report = generate_report(results, args.url, config)
    print("\n" + report)

    # Save report if requested
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\nReport saved to: {args.report}")

    # Exit with appropriate code
    all_passed = all(r['passed'] for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
