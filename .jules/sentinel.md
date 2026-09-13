## 2025-02-28 - [Fixed hardcoded /tmp path vulnerabilities in tests]
**Vulnerability:** Found multiple instances of hardcoded `/tmp` directory usages (Bandit B108) across `test_github_monitor_check_drift.py` and `test_cost_baseline.py`.
**Learning:** Hardcoded temporary paths were introduced in functional tests and mocks, leading to predictable path structures which can be exploited by malicious local users to overwrite or steal test artifacts.
**Prevention:** Always use dynamic temporary directories via `tempfile.gettempdir()` or pytest's `tmp_path` fixture for temporary file allocations to guarantee unpredictability and prevent collisions/tampering.
