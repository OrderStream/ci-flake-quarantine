# ci-flake-quarantine 🛡️

[![PyPI](https://img.shields.io/pypi/v/orderstream-ci-flake-quarantine.svg)](https://pypi.org/project/orderstream-ci-flake-quarantine/)
[![GitHub Action](https://img.shields.io/badge/GitHub%20Action-v1.0.0-orange?logo=githubactions)](https://github.com/OrderStream/ci-flake-quarantine)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://img.shields.io/badge/CI-Passing-brightgreen.svg)]()
[![OrderStream Polar](https://img.shields.io/badge/Polar-OrderStream-blue.svg)](https://polar.sh/OrderStream)
[![Stellar XLM/USDC](https://img.shields.io/badge/Stellar-USDC%2FXLM-black.svg)](#direct-web3-wallet-monetization)
[![Base USDC](https://img.shields.io/badge/Base-USDC-0052FF.svg)](#direct-web3-wallet-monetization)

Automated test-runner wrapper and GitHub Action that intercepts non-deterministic flaky test failures in CI, isolates them with deterministic clock sandboxing, and prevents costly 40-minute matrix rebuilds.

---

## 💥 The Friction & Dollar Cost
Flaky tests are the #1 source of developer fatigue and CI cloud waste:
- A single race condition or timezone-dependent test fails in a 10-node matrix run.
- The entire build turns red, wasting **$50–$300 per day** in GitHub Actions compute hours.
- Engineers are forced to re-trigger builds manually, destroying velocity.

**ci-flake-quarantine** wraps your test runner (`pytest`, `vitest`, `jest`, `cargo test`). When a failure occurs:
1. It automatically intercepts the specific failing test identifier.
2. Re-runs it under an isolated deterministic sandbox (`FAKETIME`, `PYTHONHASHSEED`, fixed timezone, mock clock).
3. If it passes in isolation, it logs the test into `.flake-quarantine.json`, reports the flake, and returns exit code `0` so your PR doesn't fail.
4. Generates a quarantine health report and audit trail.

---

## 🚀 Quick Start

### Installation
```bash
pip install ci-flake-quarantine
```

### CLI Usage
```bash
# Wrap your existing pytest command
ci-flake-quarantine run --cmd "pytest tests/"

# Enforce quarantine with max 3 deterministic retries
ci-flake-quarantine run --cmd "pytest -v" --max-retries 3

# View all quarantined tests and their pass/flake ratio
ci-flake-quarantine list

# View quarantine statistics
ci-flake-quarantine stats

# Remove fixed test from quarantine
ci-flake-quarantine remove --test-id "tests/test_api.py::test_race_condition"

# Check license & direct wallet addresses
ci-flake-quarantine license
```

---

## 🤖 GitHub Action Integration

Add this step to your GitHub Actions workflow (`.github/workflows/ci.yml`):

```yaml
- name: Run Tests with Flake Quarantine
  uses: OrderStream/ci-flake-quarantine@v1
  with:
    command: "pytest tests/"
    quarantine_file: ".flake-quarantine.json"
    max_retries: 2
    fail_on_quarantine: false
```

---

## 💰 Direct Web3 Wallet Monetization & Polar Integration

We believe in open-source sustainability with **0 platform fees**. Support this project or purchase enterprise support directly:

- **Polar Subscription & Sponsorship:** [https://polar.sh/orderstream](https://polar.sh/orderstream)
- **Stellar Network (Native XLM / USDC):**
  - Public Key: `GABFQIK63R2NETJM7T673EAMZN4RJLLGP3OFUEJU5ZVTGWUKULZJNL6`
  - Memo (Required): `400566831`
- **EVM (Base / Arbitrum / Ethereum USDT & USDC):**
  - Address: `0x5de2b62434754bfd39ef350a3a867ed3eced5074`

Set your license key via environment variable:
```bash
export ORDERSTREAM_LICENSE_KEY="ord_ent_your_license_key"
```
