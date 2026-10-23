"""
Comprehensive test suite for ci-flake-quarantine.
"""

import json
import pytest
from pathlib import Path
from ci_flake_quarantine.core import QuarantineRegistry, FlakeInterceptor, QuarantinedTest
from ci_flake_quarantine.monetization import LicenseManager
from ci_flake_quarantine.cli import main

def test_license_manager():
    # Test community tier default
    comm = LicenseManager.get_tier(None)
    assert comm["tier"] == "community"
    assert comm["is_commercial"] is False

    # Test pro tier
    pro = LicenseManager.get_tier("ord_pro_12345")
    assert pro["tier"] == "pro"
    assert pro["is_commercial"] is True

    # Test enterprise tier
    ent = LicenseManager.get_tier("ord_ent_99999")
    assert ent["tier"] == "enterprise"
    assert "priority_support" in ent["features"]

    # Test banner & footer
    banner = LicenseManager.get_banner("test-tool")
    assert "GABFQIK63R2NETJM7T673EAMZN4RJLLGP3OFUEJU5ZVTGWUKULZJNL6" in banner
    assert "0x5de2b62434754bfd39ef350a3a867ed3eced5074" in banner

    footer = LicenseManager.get_remediation_footer()
    assert "polar.sh/orderstream" in footer

def test_quarantine_registry_operations(tmp_path):
    db_file = tmp_path / "test-quarantine.json"
    registry = QuarantineRegistry(str(db_file))

    assert len(registry.tests) == 0

    # Record first flake
    qt = registry.record_flake(
        test_id="tests/test_foo.py::test_flaky_clock",
        reason="Mock failure in CI",
        deterministic_pass=True
    )
    assert qt.test_id == "tests/test_foo.py::test_flaky_clock"
    assert qt.flake_count == 1
    assert registry.is_quarantined("tests/test_foo.py::test_flaky_clock")

    # Record second flake on same test
    qt2 = registry.record_flake(
        test_id="tests/test_foo.py::test_flaky_clock",
        reason="Second flake",
        deterministic_pass=True
    )
    assert qt2.flake_count == 2

    # Graduate test
    assert registry.graduate_test("tests/test_foo.py::test_flaky_clock") is True
    assert registry.is_quarantined("tests/test_foo.py::test_flaky_clock") is False

    # Stats
    stats = registry.get_stats()
    assert stats["total_tracked"] == 1
    assert stats["graduated"] == 1

    # Remove
    assert registry.remove_test("tests/test_foo.py::test_flaky_clock") is True
    assert len(registry.tests) == 0

def test_extract_failed_tests():
    sample_pytest_output = """
============================= test session starts =============================
rootdir: /repo
collected 5 items

tests/test_a.py .F...                                                    [100%]

================================== FAILURES ===================================
______________________________ test_flaky_network ______________________________
FAILED tests/test_a.py::test_flaky_network - TimeoutError: Server took too long
FAILED tests/test_b.py::test_clock_drift - AssertionError: 10 != 12
=========================== short test summary info ===========================
FAILED tests/test_a.py::test_flaky_network
FAILED tests/test_b.py::test_clock_drift
========================= 2 failed, 3 passed in 0.45s =========================
"""
    failed = FlakeInterceptor.extract_failed_tests(sample_pytest_output)
    assert "tests/test_a.py::test_flaky_network" in failed
    assert "tests/test_b.py::test_clock_drift" in failed

def test_flake_interceptor_execution_pass(tmp_path):
    registry = QuarantineRegistry(str(tmp_path / "q.json"))
    res = FlakeInterceptor.execute_with_quarantine(
        cmd="python -c \"print('All tests passed')\"",
        registry=registry,
    )
    assert res["exit_code"] == 0
    assert res["all_passed"] is True
    assert len(res["flaky_tests_detected"]) == 0

def test_cli_subcommands(tmp_path, monkeypatch):
    db_file = str(tmp_path / "q_cli.json")
    
    # Run license command
    exit_code = main(["license"])
    assert exit_code == 0

    # Run stats on empty
    exit_code = main(["stats", "--quarantine-file", db_file])
    assert exit_code == 0

    # List empty
    exit_code = main(["list", "--quarantine-file", db_file])
    assert exit_code == 0

def test_extract_jest_and_unittest_failures():
    jest_out = """
    FAIL src/auth.test.ts
    ● Auth > rejects invalid bearer token
    ● Auth > times out on stale nonce
    """
    failed = FlakeInterceptor.extract_failed_tests(jest_out)
    assert "Auth > rejects invalid bearer token" in failed
    assert "Auth > times out on stale nonce" in failed

    unittest_out = """
    ERROR: test_db_pool (test_core.DatabaseTests)
    FAIL: test_race_condition (test_core.AsyncTests)
    """
    failed_unit = FlakeInterceptor.extract_failed_tests(unittest_out)
    assert "test_core.DatabaseTests.test_db_pool" in failed_unit
    assert "test_core.AsyncTests.test_race_condition" in failed_unit

def test_flake_quarantine_failure_interception(tmp_path):
    q_file = tmp_path / "flaky_run.json"
    registry = QuarantineRegistry(str(q_file))

    # Simulate command that fails with a pytest failure line
    fail_script = tmp_path / "fake_fail.py"
    fail_script.write_text("import sys; print('FAILED tests/test_net.py::test_timeout'); sys.exit(1)", encoding="utf-8")

    res = FlakeInterceptor.execute_with_quarantine(
        cmd=f'python "{fail_script}"',
        registry=registry,
        quarantine_passes_ci=True
    )
    # Since quarantine_passes_ci is True, exit code is 0 (saved matrix rebuild)
    assert res["exit_code"] == 0
    assert res["quarantine_applied"] is True
    assert "tests/test_net.py::test_timeout" in res["flaky_tests_detected"]
    assert registry.is_quarantined("tests/test_net.py::test_timeout")

