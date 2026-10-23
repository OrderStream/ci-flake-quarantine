"""
Command line interface for ci-flake-quarantine.
"""

import argparse
import sys
import json
from ci_flake_quarantine.core import QuarantineRegistry, FlakeInterceptor
from ci_flake_quarantine.monetization import LicenseManager

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ci-flake-quarantine",
        description="Automated CI flaky test quarantine runner with deterministic clock sandboxing"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # run command
    run_parser = subparsers.add_parser("run", help="Run test command under quarantine wrapper")
    run_parser.add_argument("--cmd", required=True, help="Test command to run (e.g. 'pytest' or 'npm test')")
    run_parser.add_argument("--quarantine-file", default=".flake-quarantine.json", help="Path to quarantine database")
    run_parser.add_argument("--max-retries", type=int, default=2, help="Number of sandboxed retries")
    run_parser.add_argument("--freeze-clock", action="store_true", default=True, help="Enable deterministic clock freeze")
    run_parser.add_argument("--fail-on-quarantine", action="store_true", default=False, help="Fail CI even if tests quarantined")
    run_parser.add_argument("--license-key", default=None, help="OrderStream license key")

    # list command
    list_parser = subparsers.add_parser("list", help="List quarantined tests")
    list_parser.add_argument("--quarantine-file", default=".flake-quarantine.json", help="Path to quarantine database")

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Display flakiness statistics")
    stats_parser.add_argument("--quarantine-file", default=".flake-quarantine.json", help="Path to quarantine database")

    # remove command
    remove_parser = subparsers.add_parser("remove", help="Remove test from quarantine")
    remove_parser.add_argument("--test-id", required=True, help="Test identifier to remove")
    remove_parser.add_argument("--quarantine-file", default=".flake-quarantine.json", help="Path to quarantine database")

    # license / donate command
    subparsers.add_parser("license", help="View license tier and 0% fee crypto donation wallets")

    args = parser.parse_args(argv)

    if not args.command or args.command == "license":
        print(LicenseManager.get_banner("ci-flake-quarantine"))
        tier = LicenseManager.get_tier(getattr(args, "license_key", None))
        print(f"Active Tier: {tier['name']} ({tier['tier']})")
        print(f"Features: {', '.join(tier['features'])}")
        print(LicenseManager.get_remediation_footer())
        return 0

    if args.command == "run":
        print(LicenseManager.get_banner("ci-flake-quarantine"))
        registry = QuarantineRegistry(args.quarantine_file)
        result = FlakeInterceptor.execute_with_quarantine(
            cmd=args.cmd,
            registry=registry,
            max_retries=args.max_retries,
            freeze_clock=args.freeze_clock,
            quarantine_passes_ci=not args.fail_on_quarantine
        )
        print(result["output"])
        if result["quarantine_applied"]:
            print(f"\n[CI-FLAKE-QUARANTINE] Intercepted {len(result['flaky_tests_detected'])} flaky test(s).")
            for t in result["flaky_tests_detected"]:
                print(f"  -> Quarantined: {t}")
            print("[CI-FLAKE-QUARANTINE] Successfully prevented 40-minute matrix rebuild!")
            print(LicenseManager.get_remediation_footer())
        return result["exit_code"]

    elif args.command == "list":
        registry = QuarantineRegistry(args.quarantine_file)
        active = [t for t in registry.tests.values() if t.status == "quarantined"]
        print(f"Active Quarantined Tests ({len(active)}):")
        for t in active:
            print(f"- {t.test_id} (flakes: {t.flake_count}, deterministic_pass: {t.deterministic_pass})")
            print(f"  Reason: {t.reason}")
        return 0

    elif args.command == "stats":
        registry = QuarantineRegistry(args.quarantine_file)
        stats = registry.get_stats()
        print(json.dumps(stats, indent=2))
        return 0

    elif args.command == "remove":
        registry = QuarantineRegistry(args.quarantine_file)
        if registry.remove_test(args.test_id):
            print(f"Successfully removed '{args.test_id}' from quarantine.")
            return 0
        else:
            print(f"Test '{args.test_id}' not found in quarantine.")
            return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
