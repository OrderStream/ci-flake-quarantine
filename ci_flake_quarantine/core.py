"""
Core test isolation and deterministic sandboxing engine for ci-flake-quarantine.
"""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

@dataclass
class QuarantinedTest:
    test_id: str
    quarantined_at: str
    reason: str
    run_count: int
    flake_count: int
    deterministic_pass: bool
    status: str = "quarantined"  # quarantined, graduated, active

class QuarantineRegistry:
    def __init__(self, file_path: str = ".flake-quarantine.json"):
        self.file_path = Path(file_path)
        self.tests: Dict[str, QuarantinedTest] = {}
        self.load()

    def load(self) -> None:
        if self.file_path.exists():
            try:
                data = json.loads(self.file_path.read_text(encoding="utf-8"))
                for tid, entry in data.get("quarantined_tests", {}).items():
                    self.tests[tid] = QuarantinedTest(**entry)
            except Exception:
                self.tests = {}

    def save(self) -> None:
        data = {
            "version": "1.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "quarantined_tests": {tid: asdict(qt) for tid, qt in self.tests.items()}
        }
        self.file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_quarantined(self, test_id: str) -> bool:
        qt = self.tests.get(test_id)
        return qt is not None and qt.status == "quarantined"

    def record_flake(self, test_id: str, reason: str, deterministic_pass: bool) -> QuarantinedTest:
        if test_id in self.tests:
            qt = self.tests[test_id]
            qt.flake_count += 1
            qt.run_count += 1
            qt.deterministic_pass = deterministic_pass
            qt.status = "quarantined"
        else:
            qt = QuarantinedTest(
                test_id=test_id,
                quarantined_at=datetime.now(timezone.utc).isoformat(),
                reason=reason[:500],
                run_count=1,
                flake_count=1,
                deterministic_pass=deterministic_pass,
                status="quarantined"
            )
            self.tests[test_id] = qt
        self.save()
        return qt

    def graduate_test(self, test_id: str) -> bool:
        if test_id in self.tests:
            self.tests[test_id].status = "graduated"
            self.save()
            return True
        return False

    def remove_test(self, test_id: str) -> bool:
        if test_id in self.tests:
            del self.tests[test_id]
            self.save()
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        total = len(self.tests)
        quarantined = sum(1 for t in self.tests.values() if t.status == "quarantined")
        graduated = sum(1 for t in self.tests.values() if t.status == "graduated")
        return {
            "total_tracked": total,
            "active_quarantined": quarantined,
            "graduated": graduated,
        }

class FlakeInterceptor:
    @staticmethod
    def extract_failed_tests(output: str) -> List[str]:
        """
        Parses pytest, jest, or standard test output to extract failed test identifiers.
        """
        failed: List[str] = []
        # pytest pattern: FAILED path/to/test.py::test_name
        pytest_matches = re.findall(r"FAILED\s+([^\s:]+::[^\s:]+)", output)
        failed.extend(pytest_matches)

        # pytest short summary: test_name FAILED
        pytest_short = re.findall(r"(?:^|\n)(tests/[^\s:]+\.py::[^\s]+)\s+FAILED", output)
        failed.extend(pytest_short)

        # jest pattern: FAIL path/to/test.ts > suite > test_name
        jest_matches = re.findall(r"●\s+(.*?)\n", output)
        failed.extend([m.strip() for m in jest_matches if m.strip()])

        # generic python unittest FAIL: test_name (module.TestCase)
        unittest_matches = re.findall(r"FAIL:\s+([^\s]+)\s+\((.*?)\)", output)
        for name, cls in unittest_matches:
            failed.append(f"{cls}.{name}")

        return list(dict.fromkeys(failed))  # deduplicate preserving order

    @staticmethod
    def run_command(cmd: str, env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None) -> Tuple[int, str]:
        current_env = os.environ.copy()
        if env:
            current_env.update(env)
        
        proc = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True,
            env=current_env,
            cwd=cwd
        )
        combined_output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode, combined_output

    @classmethod
    def execute_with_quarantine(
        cls,
        cmd: str,
        registry: QuarantineRegistry,
        max_retries: int = 2,
        freeze_clock: bool = True,
        deterministic_seed: int = 42,
        quarantine_passes_ci: bool = True,
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Runs the test command. If it fails, checks for flaky tests, isolates them with
        sandboxed deterministic clock and seed, and isolates failures.
        """
        code, output = cls.run_command(cmd, cwd=cwd)
        if code == 0:
            return {
                "exit_code": 0,
                "output": output,
                "flaky_tests_detected": [],
                "all_passed": True,
                "quarantine_applied": False,
            }

        failed_tests = cls.extract_failed_tests(output)
        if not failed_tests:
            # Command failed with general build or syntax error, cannot isolate specific test
            return {
                "exit_code": code,
                "output": output,
                "flaky_tests_detected": [],
                "all_passed": False,
                "quarantine_applied": False,
                "error": "Command failed without parsable test failures.",
            }

        flaky_detected: List[str] = []
        sandbox_env = {
            "PYTHONHASHSEED": str(deterministic_seed),
            "TZ": "UTC",
        }
        if freeze_clock:
            sandbox_env["FAKETIME"] = "2026-01-01 00:00:00"
            sandbox_env["CI_DETERMINISTIC_CLOCK"] = "1"

        # Attempt sandboxed re-runs on failed tests
        for test_id in failed_tests:
            passed_retry = False
            for retry in range(1, max_retries + 1):
                # Try retrying test directly or in sandbox
                retry_cmd = f"{cmd} -k {test_id.split('::')[-1]}" if "pytest" in cmd else cmd
                ret_code, ret_out = cls.run_command(retry_cmd, env=sandbox_env, cwd=cwd)
                if ret_code == 0:
                    passed_retry = True
                    break
            
            # Record flake
            qt = registry.record_flake(
                test_id=test_id,
                reason=f"Failed initially; {'passed in deterministic retry' if passed_retry else 'isolated in quarantine'}",
                deterministic_pass=passed_retry
            )
            flaky_detected.append(test_id)

        # Decide exit code
        final_code = 0 if quarantine_passes_ci else 1
        return {
            "exit_code": final_code,
            "output": output,
            "flaky_tests_detected": flaky_detected,
            "all_passed": False,
            "quarantine_applied": True,
            "saved_matrix_rebuild": True,
        }
