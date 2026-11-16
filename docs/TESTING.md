# Testing

## Automated tests

```bash
cd backend
python -m pytest                       # SQLite: two app instances (hospital + cloud) wired over signed HTTP
```

To run against real PostgreSQL, which also enables the true parallel row-locking test, point the suite at two **disposable** databases. They are wiped.

```bash
TEST_HOSPITAL_DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/test_hospital \
TEST_CLOUD_DATABASE_URL=postgresql+psycopg://u:p@localhost:5432/test_cloud python -m pytest
```

Outages are simulated by swapping the peer HTTP client for one that raises connection errors.

| # | Required scenario | Test |
|---|---|---|
| 1 | Billing with internet | `test_billing.py::test_1_billing_with_internet` |
| 2 | Billing during internet outage | `test_billing.py::test_2_billing_during_internet_outage` |
| 3 | Stock deduction across multiple computers | `test_billing.py::test_3_stock_deduction_across_terminals` |
| 4 | Remote access, hospital reachable | `test_sync.py::test_4_remote_billing_when_hospital_reachable` |
| 5 | Remote access, hospital unavailable | `test_sync.py::test_5_remote_access_when_hospital_unavailable` |
| 6 | Sync after connectivity restored | `test_sync.py::test_6_sync_after_connectivity_restored` |
| 7 | Duplicate sync prevention | `test_sync.py::test_7_duplicate_synchronization_prevention`, `test_billing.py::test_idempotent_bill_submission` |
| 8 | Concurrent stock deduction | `test_billing.py::test_8_…` (rollback + oversell guard), `test_8b_true_parallel_deduction` (PostgreSQL) |
| 9 | Bill reversal and stock restoration | `test_billing.py::test_9_bill_reversal_restores_stock` |
| 10 | Offline login | `test_auth_and_workflows.py::test_10_offline_login`, `test_first_time_verification_via_cloud_otp` |
| 11 | Offline low-stock alerts | `test_billing.py::test_11_offline_low_stock_alert` |
| 12 | Approval workflows (Biller requests, Admin approves; Admin applies directly) | `test_auth_and_workflows.py::test_12_approval_workflow`, `test_rate_change_enables_billing` |
| 13 | Backup and restoration | `test_13_migrations_build_schema` + `deploy/backup/restore-test.sh` (weekly, against real backups) |
| 14 | Sync failure and recovery | `test_sync.py::test_14_sync_failure_and_recovery`, `test_14b_conflict_detected_held_and_resolved` |

Security tests: forged or unsigned peer requests are rejected, remote role restrictions match local ones, OTP rate limiting works, refresh tokens rotate, revoked sessions stop working, only the Admin and Biller roles exist, the last Admin cannot be removed, and user-directory changes require internet.

Frontend: `cd frontend && npm run build` runs the TypeScript type check and produces the production bundle.

## Manual acceptance test (on the real servers)

1. **Billing online:** at PC-1 create a bill. The receipt prints, and the bill appears in the cloud within seconds.
2. **Outage:** unplug the hospital WAN. The banner turns amber. Bill at PC-1 and PC-2, and sign in again offline with a verified account.
3. **Remote unavailable:** with the WAN still unplugged, the cloud shows the red banner, New bill is disabled, and reports still display.
4. **Recovery:** plug the WAN back in. Pending drains to 0. Counts and stock match on both sides (Stock page on hospital vs cloud).
5. **Concurrency:** two PCs bill the last units of the same medicine at the same moment. One succeeds; the other gets "Insufficient stock".
6. **Reversal:** an Admin reverses a bill. The stock is restored, and the ledger shows a "Bill reversal" entry.
7. **Alerts:** bill a medicine down to 50 units or fewer. The toast reads exactly: `LOW STOCK ALERT: <name> — <n> units remaining.`
8. **Approvals:** a Biller requests +100. Stock is unchanged until the Admin approves it. A change made by the Admin applies immediately.
9. **Backups:** run `backup.sh` and `restore-test.sh` manually. The result must be `RESULT: PASSED`.

First-time sign-up: `test_setup.py` (sign-up on the hospital or cloud, refused once an account exists, needs internet once at the hospital, then works offline).
