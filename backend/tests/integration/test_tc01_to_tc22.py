"""Integration test suite covering TC01–TC05, TC08–TC22 against REAL PostgreSQL 16."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import psycopg
import pytest
from app.core.clock import Clock
from app.main import create_app
from app.services.auth_service import AuthService
from app.services.idempotency_service import FaultHooks
from app.services.sso_service import SSO_BIND_COOKIE_NAME, SsoService
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from scripts.check_invariants import run_invariant_checks
from scripts.seed import KEYCLOAK_SV0001_SUB, LAB_DEMO_PASSWORD
from tests.conftest import auth_headers, login_and_get_tokens, make_test_settings

pytestmark = pytest.mark.integration


def test_tc01_login_success_and_invalid_credentials(client: TestClient) -> None:
    # Valid STUDENT login
    r_ok = client.post(
        "/api/v1/auth/login",
        json={"student_id": "SV0001", "password": LAB_DEMO_PASSWORD},
    )
    assert r_ok.status_code == 200
    body = r_ok.json()
    assert body["success"] is True
    assert body["code"] == "LOGIN_SUCCESS"
    data = body["data"]
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 3600
    assert data["refresh_expires_in"] == 28800
    assert len(data["access_token"]) >= 43
    assert len(data["refresh_token"]) >= 43
    assert data["student"] == {
        "student_id": "SV0001",
        "full_name": "Sinh viên mẫu 0001",
        "role": "STUDENT",
    }

    # Wrong password -> generic 401 INVALID_CREDENTIALS
    r_wrong_pw = client.post(
        "/api/v1/auth/login",
        json={"student_id": "SV0001", "password": "WrongPassword123"},
    )
    assert r_wrong_pw.status_code == 401
    assert r_wrong_pw.json()["code"] == "INVALID_CREDENTIALS"
    assert r_wrong_pw.headers["WWW-Authenticate"] == "Bearer"

    # Non-existent user -> identical 401 INVALID_CREDENTIALS message (no user enumeration)
    r_no_user = client.post(
        "/api/v1/auth/login",
        json={"student_id": "SV9999", "password": LAB_DEMO_PASSWORD},
    )
    assert r_no_user.status_code == 401
    assert r_no_user.json()["code"] == "INVALID_CREDENTIALS"
    assert r_no_user.json()["message"] == r_wrong_pw.json()["message"]


def test_tc02_tc03_register_once_caller_views_and_already_registered(
    client: TestClient,
) -> None:
    sv1 = login_and_get_tokens(client, "SV0001")
    sv2 = login_and_get_tokens(client, "SV0002")
    admin = login_and_get_tokens(client, "AD0001")

    # TC02: Register SV0001 on LHP001 (50 seats -> 49 remaining)
    idem_1 = str(uuid.uuid4())
    r_reg = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": idem_1}),
        json={"student_id": "SV0001", "course_class_id": "LHP001"},
    )
    assert r_reg.status_code == 200
    reg_data = r_reg.json()["data"]
    reg_id = reg_data["registration"]["registration_id"]
    assert reg_data["registration"]["status"] == "ACTIVE"
    assert reg_data["registration"]["payment_status"] == "UNPAID"
    assert reg_data["registration"]["tuition_amount"] == 1500000
    assert reg_data["registration"]["cancelled_at"] is None
    assert reg_data["registration"]["registered_at"].endswith("Z")
    assert reg_data["course_class"]["remaining_seats"] == 49
    assert reg_data["course_class"]["registered_count"] == 1
    assert reg_data["course_class"]["registration_status"] == "REGISTERED"
    assert reg_data["course_class"]["registration_id"] == reg_id

    # SV0002 sees remaining_seats=49, NOT_REGISTERED, prerequisites[0].satisfied=False
    r_sv2_detail = client.get(
        "/api/v1/course-classes/LHP001",
        headers=auth_headers(sv2["access_token"]),
    )
    assert r_sv2_detail.status_code == 200
    cc_sv2 = r_sv2_detail.json()["data"]["course_class"]
    assert cc_sv2["remaining_seats"] == 49
    assert cc_sv2["registration_status"] == "NOT_REGISTERED"
    assert cc_sv2["registration_id"] is None
    assert cc_sv2["prerequisites"][0]["satisfied"] is False

    # ADMIN sees NOT_REGISTERED and prerequisites[0].satisfied=None
    r_adm_detail = client.get(
        "/api/v1/course-classes/LHP001",
        headers=auth_headers(admin["access_token"]),
    )
    cc_adm = r_adm_detail.json()["data"]["course_class"]
    assert cc_adm["registration_status"] == "NOT_REGISTERED"
    assert cc_adm["prerequisites"][0]["satisfied"] is None

    # TC03: Same student + same class with NEW Idempotency-Key -> 409 ALREADY_REGISTERED
    r_dup = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001", "course_class_id": "LHP001"},
    )
    assert r_dup.status_code == 409
    assert r_dup.json()["code"] == "ALREADY_REGISTERED"

    # Seat count stays 49
    r_check = client.get(
        "/api/v1/course-classes/LHP001",
        headers=auth_headers(sv1["access_token"]),
    )
    assert r_check.json()["data"]["course_class"]["remaining_seats"] == 49


def test_tc04_tc05_tc08_tc09_class_full_closed_mismatch_and_not_found(
    client: TestClient,
    clean_db: str,
) -> None:
    sv1 = login_and_get_tokens(client, "SV0001")
    sv2 = login_and_get_tokens(client, "SV0002")
    admin = login_and_get_tokens(client, "AD0001")

    # TC08: Token SV0001 with body SV0002 -> 403 STUDENT_MISMATCH
    r_mismatch = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0002", "course_class_id": "LHP003"},
    )
    assert r_mismatch.status_code == 403
    assert r_mismatch.json()["code"] == "STUDENT_MISMATCH"

    # TC09: Missing field / invalid ID / non-existent class LHP999
    r_missing = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001"},
    )
    assert r_missing.status_code == 400
    assert r_missing.json()["code"] == "VALIDATION_ERROR"

    r_not_found = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001", "course_class_id": "LHP999"},
    )
    assert r_not_found.status_code == 404
    assert r_not_found.json()["code"] == "CLASS_NOT_FOUND"

    # TC04: Class with capacity=1 becomes full -> second student gets 409 CLASS_FULL
    r_create = client.post(
        "/api/v1/admin/course-classes",
        headers=auth_headers(admin["access_token"]),
        json={
            "class_code": "FULL-01",
            "course_code": "JAVA",
            "course_name": "Lớp giới hạn 1 chỗ",
            "credits": 3,
            "capacity": 1,
            "status": "OPEN",
            "schedule": [],
            "prerequisite_course_codes": [],
        },
    )
    assert r_create.status_code == 201
    one_seat_id = r_create.json()["data"]["course_class"]["course_class_id"]

    assert (
        client.post(
            "/api/v1/register",
            headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
            json={"student_id": "SV0001", "course_class_id": one_seat_id},
        ).status_code
        == 200
    )

    r_full = client.post(
        "/api/v1/register",
        headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0002", "course_class_id": one_seat_id},
    )
    assert r_full.status_code == 409
    assert r_full.json()["code"] == "CLASS_FULL"

    # TC05: Close LHP003 -> SV0002 gets 409 REGISTRATION_CLOSED
    r_close = client.patch(
        "/api/v1/admin/course-classes/LHP003/status",
        headers=auth_headers(admin["access_token"]),
        json={"status": "CLOSED"},
    )
    assert r_close.status_code == 200

    r_closed = client.post(
        "/api/v1/register",
        headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0002", "course_class_id": "LHP003"},
    )
    assert r_closed.status_code == 409
    assert r_closed.json()["code"] == "REGISTRATION_CLOSED"


def test_tc10_tc11_rollback_on_mid_write_failure_and_replay_after_lost_response(
    client: TestClient,
    clean_db: str,
) -> None:
    sv1 = login_and_get_tokens(client, "SV0001")
    sv2 = login_and_get_tokens(client, "SV0002")
    admin = login_and_get_tokens(client, "AD0001")

    # TC10: Inject crash right after INSERT INTO registrations, BEFORE decrementing seats
    def _boom_mid_tx() -> None:
        raise RuntimeError("Simulated crash between INSERT registration and UPDATE seats")

    FaultHooks.after_registration_insert = _boom_mid_tx
    crash_key = str(uuid.uuid4())
    r_crash = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": crash_key}),
        json={"student_id": "SV0001", "course_class_id": "LHP003"},
    )
    FaultHooks.reset()
    assert r_crash.status_code == 500
    assert r_crash.json()["code"] == "INTERNAL_ERROR"

    # Verify PostgreSQL rolled back BOTH registration and idempotency_records, and seats remain 50!
    with psycopg.connect(clean_db, row_factory=dict_row) as conn:
        reg_cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM registrations WHERE course_class_id = 'LHP003'"
        ).fetchone()["c"]
        idem_cnt = conn.execute("SELECT COUNT(*) AS c FROM idempotency_records").fetchone()["c"]
        rem = conn.execute(
            "SELECT remaining_seats FROM course_classes WHERE course_class_id = 'LHP003'"
        ).fetchone()["remaining_seats"]
        assert reg_cnt == 0
        assert idem_cnt == 0
        assert rem == 50

    # TC11: Simulate lost response AFTER PostgreSQL COMMIT
    def _drop_after_commit() -> None:
        raise ConnectionError("Simulated socket drop after PostgreSQL COMMIT")

    FaultHooks.after_commit_before_response = _drop_after_commit
    lost_key = str(uuid.uuid4())
    r_dropped = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": lost_key}),
        json={"student_id": "SV0001", "course_class_id": "LHP003"},
    )
    FaultHooks.reset()
    assert r_dropped.status_code == 500  # Client never received the success response

    # Retry with the EXACT SAME Idempotency-Key -> replays stored 200 REGISTERED without 2nd write!
    r_replay = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": lost_key}),
        json={"student_id": "SV0001", "course_class_id": "LHP003"},
    )
    assert r_replay.status_code == 200
    assert r_replay.headers.get("Idempotent-Replayed") == "true"
    replay_body = r_replay.json()
    assert replay_body["code"] == "REGISTERED"
    assert r_replay.headers["X-Request-ID"] == replay_body["request_id"]
    assert replay_body["data"]["course_class"]["remaining_seats"] == 49

    # Also verify business error replay: if key got CLASS_FULL, same key replays CLASS_FULL even after seat frees up!
    c1 = client.post(
        "/api/v1/admin/course-classes",
        headers=auth_headers(admin["access_token"]),
        json={
            "class_code": "ERR-REPLAY-01",
            "course_code": "JAVA",
            "course_name": "Kiểm tra replay lỗi",
            "credits": 3,
            "capacity": 1,
            "status": "OPEN",
            "schedule": [],
            "prerequisite_course_codes": [],
        },
    ).json()["data"]["course_class"]["course_class_id"]

    reg_sv1 = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001", "course_class_id": c1},
    ).json()["data"]["registration"]["registration_id"]

    err_key = str(uuid.uuid4())
    r_err1 = client.post(
        "/api/v1/register",
        headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": err_key}),
        json={"student_id": "SV0002", "course_class_id": c1},
    )
    assert r_err1.status_code == 409
    assert r_err1.json()["code"] == "CLASS_FULL"
    orig_err_req_id = r_err1.json()["request_id"]

    # SV0001 cancels so 1 seat is now free
    assert (
        client.delete(
            f"/api/v1/registrations/{reg_sv1}",
            headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        ).status_code
        == 200
    )

    # SV0002 re-sending old `err_key` MUST still replay `409 CLASS_FULL`!
    r_err_replay = client.post(
        "/api/v1/register",
        headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": err_key}),
        json={"student_id": "SV0002", "course_class_id": c1},
    )
    assert r_err_replay.status_code == 409
    assert r_err_replay.headers.get("Idempotent-Replayed") == "true"
    assert r_err_replay.json()["code"] == "CLASS_FULL"
    assert r_err_replay.json()["request_id"] == orig_err_req_id

    # Using a NEW key now succeeds!
    r_new_intent = client.post(
        "/api/v1/register",
        headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0002", "course_class_id": c1},
    )
    assert r_new_intent.status_code == 200


def test_tc12_pg_dump_and_pg_restore_snapshot_verification(
    client: TestClient,
    pg_admin_uri: str,
    clean_db: str,
    tmp_path: Path,
) -> None:
    from urllib.parse import urlparse, urlunparse

    sv1 = login_and_get_tokens(client, "SV0001")
    sv2 = login_and_get_tokens(client, "SV0002")

    # 1. Create a pre-backup registration & payment in `dkhp_pytest`
    reg_resp = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001", "course_class_id": "LHP003"},
    )
    assert reg_resp.status_code == 200
    reg_id = reg_resp.json()["data"]["registration"]["registration_id"]

    pay_resp = client.post(
        "/api/v1/payments",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"registration_id": reg_id},
    )
    assert pay_resp.status_code == 200

    # 2. Take custom-format backup using real PostgreSQL 16 `pg_dump`
    pg_dump_bin: str | None = None
    pg_restore_bin: str | None = None
    try:
        import pgserver as pgserver_mod

        pg_bin_dir = Path(pgserver_mod.__file__).resolve().parent / "pginstall" / "bin"
        cand_dump = pg_bin_dir / ("pg_dump.exe" if (pg_bin_dir / "pg_dump.exe").exists() else "pg_dump")
        cand_restore = pg_bin_dir / (
            "pg_restore.exe" if (pg_bin_dir / "pg_restore.exe").exists() else "pg_restore"
        )
        if cand_dump.exists() and cand_restore.exists():
            pg_dump_bin = str(cand_dump)
            pg_restore_bin = str(cand_restore)
    except ImportError:
        pass

    if pg_dump_bin is None or pg_restore_bin is None:
        pg_dump_bin = shutil.which("pg_dump")
        pg_restore_bin = shutil.which("pg_restore")
    if pg_dump_bin is None or pg_restore_bin is None:
        pytest.skip("pg_dump/pg_restore binaries are not installed in PATH or pgserver.")

    dump_file = tmp_path / "dkhp_snapshot.dump"

    subprocess.run(
        [pg_dump_bin, "--format=custom", "--no-owner", "--no-privileges", f"--file={dump_file}", clean_db],
        check=True,
        capture_output=True,
    )

    # 3. Perform a POST-backup registration (must NOT appear in restored snapshot, while live DB keeps it)
    post_backup_resp = client.post(
        "/api/v1/register",
        headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0002", "course_class_id": "LHP002"},
    )
    assert post_backup_resp.status_code == 200

    # 4. Restore into a completely separate database `dkhp_restore_verify_test`
    restore_db_name = "dkhp_restore_verify_test"
    with psycopg.connect(pg_admin_uri, autocommit=True) as adm_conn:
        adm_conn.execute(f'DROP DATABASE IF EXISTS "{restore_db_name}"')
        adm_conn.execute(f'CREATE DATABASE "{restore_db_name}"')

    parsed_clean = urlparse(clean_db)
    restore_uri = urlunparse(parsed_clean._replace(path=f"/{restore_db_name}"))
    try:
        subprocess.run(
            [pg_restore_bin, "--no-owner", "--no-privileges", f"--dbname={restore_uri}", str(dump_file)],
            check=True,
            capture_output=True,
        )

        # Verify restored DB matches snapshot at dump time AND passes all SQL invariants!
        inv_restored = run_invariant_checks(restore_uri)
        assert inv_restored["ok"], inv_restored
        assert inv_restored["stats"]["active_registrations"] == 1
        assert inv_restored["stats"]["paid_payments"] == 1

        # Verify live DB still has 2 active registrations (never overwritten!)
        inv_live = run_invariant_checks(clean_db)
        assert inv_live["ok"]
        assert inv_live["stats"]["active_registrations"] == 2
    finally:
        with psycopg.connect(pg_admin_uri, autocommit=True) as adm_conn:
            adm_conn.execute(f'DROP DATABASE IF EXISTS "{restore_db_name}"')
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_tc13_tc14_tc17_cancel_replay_reregister_and_payment_refund(
    client: TestClient,
) -> None:
    sv1 = login_and_get_tokens(client, "SV0001")
    admin = login_and_get_tokens(client, "AD0001")

    # Register LHP001
    r1 = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001", "course_class_id": "LHP001"},
    )
    reg1_id = r1.json()["data"]["registration"]["registration_id"]

    # Even if admin closes LHP001, student CAN still cancel!
    client.patch(
        "/api/v1/admin/course-classes/LHP001/status",
        headers=auth_headers(admin["access_token"]),
        json={"status": "CLOSED"},
    )

    # TC13: Cancel unpaid registration -> refund is null, remaining_seats back to 50
    cancel_key = str(uuid.uuid4())
    c1 = client.delete(
        f"/api/v1/registrations/{reg1_id}",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": cancel_key}),
    )
    assert c1.status_code == 200
    assert c1.json()["data"]["refund"] is None
    assert c1.json()["data"]["course_class"]["remaining_seats"] == 50

    # Replay same cancel key -> 200 + Idempotent-Replayed: true, seats STILL 50
    c1_replay = client.delete(
        f"/api/v1/registrations/{reg1_id}",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": cancel_key}),
    )
    assert c1_replay.status_code == 200
    assert c1_replay.headers.get("Idempotent-Replayed") == "true"
    assert c1_replay.json()["data"]["course_class"]["remaining_seats"] == 50

    # Cancel again with NEW key -> 404 REGISTRATION_NOT_FOUND
    c1_again = client.delete(
        f"/api/v1/registrations/{reg1_id}",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
    )
    assert c1_again.status_code == 404
    assert c1_again.json()["code"] == "REGISTRATION_NOT_FOUND"

    # Reopen LHP001 and TC14: Re-register -> brand new UUID, old CANCELLED preserved
    client.patch(
        "/api/v1/admin/course-classes/LHP001/status",
        headers=auth_headers(admin["access_token"]),
        json={"status": "OPEN"},
    )
    r2 = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001", "course_class_id": "LHP001"},
    )
    assert r2.status_code == 200
    reg2_id = r2.json()["data"]["registration"]["registration_id"]
    assert reg2_id != reg1_id
    assert r2.json()["data"]["registration"]["payment_status"] == "UNPAID"

    # TC17: Pay for reg2_id -> replay -> new key ALREADY_PAID -> cancel triggers REFUNDED
    pay_key = str(uuid.uuid4())
    p1 = client.post(
        "/api/v1/payments",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": pay_key}),
        json={"registration_id": reg2_id},
    )
    assert p1.status_code == 200
    assert p1.json()["code"] == "PAYMENT_SUCCESS"
    pay_id = p1.json()["data"]["payment"]["payment_id"]
    assert p1.json()["data"]["payment"]["amount"] == 1500000
    assert p1.json()["data"]["registration"]["payment_status"] == "PAID"

    # Same key -> replay
    p1_replay = client.post(
        "/api/v1/payments",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": pay_key}),
        json={"registration_id": reg2_id},
    )
    assert p1_replay.status_code == 200
    assert p1_replay.headers.get("Idempotent-Replayed") == "true"

    # New key -> 409 ALREADY_PAID
    p2 = client.post(
        "/api/v1/payments",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"registration_id": reg2_id},
    )
    assert p2.status_code == 409
    assert p2.json()["code"] == "ALREADY_PAID"

    # Cancel paid registration -> simulated refund returned!
    c2 = client.delete(
        f"/api/v1/registrations/{reg2_id}",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
    )
    assert c2.status_code == 200
    c2_data = c2.json()["data"]
    assert c2_data["registration"]["status"] == "CANCELLED"
    assert c2_data["registration"]["payment_status"] == "REFUNDED"
    assert c2_data["refund"]["payment_id"] == pay_id
    assert c2_data["refund"]["status"] == "REFUNDED"
    assert c2_data["refund"]["amount"] == 1500000

    # Re-registering a 3rd time starts UNPAID and preserves all history!
    r3 = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001", "course_class_id": "LHP001"},
    )
    assert r3.status_code == 200
    assert r3.json()["data"]["registration"]["payment_status"] == "UNPAID"

    hist_all = client.get(
        "/api/v1/registrations/me?status=ALL",
        headers=auth_headers(sv1["access_token"]),
    ).json()["data"]
    assert hist_all["pagination"]["total_items"] == 3

    pay_hist = client.get(
        "/api/v1/payments/me?status=REFUNDED",
        headers=auth_headers(sv1["access_token"]),
    ).json()["data"]
    assert pay_hist["pagination"]["total_items"] == 1
    assert pay_hist["items"][0]["payment_id"] == pay_id


def test_tc15_tc16_schedule_conflict_and_prerequisite_missing(client: TestClient) -> None:
    sv1 = login_and_get_tokens(client, "SV0001")
    sv2 = login_and_get_tokens(client, "SV0002")

    # TC16: SV0002 has NOT completed CS101 -> LHP001 returns 409 PREREQUISITE_NOT_MET
    r_prereq = client.post(
        "/api/v1/register",
        headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0002", "course_class_id": "LHP001"},
    )
    assert r_prereq.status_code == 409
    b_prereq = r_prereq.json()
    assert b_prereq["code"] == "PREREQUISITE_NOT_MET"
    assert b_prereq["errors"][0]["field"] == "prerequisites[0].course_code"
    assert b_prereq["errors"][0]["code"] == "PREREQUISITE_MISSING"
    assert "CS101" in b_prereq["errors"][0]["message"]

    # TC15: SV0001 registers LHP001 (MON 1–3) then tries LHP002 (MON 2–4) -> 409 SCHEDULE_CONFLICT
    assert (
        client.post(
            "/api/v1/register",
            headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
            json={"student_id": "SV0001", "course_class_id": "LHP001"},
        ).status_code
        == 200
    )

    r_sched = client.post(
        "/api/v1/register",
        headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
        json={"student_id": "SV0001", "course_class_id": "LHP002"},
    )
    assert r_sched.status_code == 409
    b_sched = r_sched.json()
    assert b_sched["code"] == "SCHEDULE_CONFLICT"
    assert b_sched["errors"][0]["field"] == "schedule"
    assert b_sched["errors"][0]["code"] == "CLASS_TIME_CONFLICT"
    assert "LHP001" in b_sched["errors"][0]["message"]

    # Non-conflicting LHP003 (TUE 1–3) succeeds!
    assert (
        client.post(
            "/api/v1/register",
            headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
            json={"student_id": "SV0001", "course_class_id": "LHP003"},
        ).status_code
        == 200
    )


def test_tc18_admin_crud_rbac_capacity_rules_and_snapshot_preservation(
    client: TestClient,
) -> None:
    sv1 = login_and_get_tokens(client, "SV0001")
    sv2 = login_and_get_tokens(client, "SV0002")
    admin = login_and_get_tokens(client, "AD0001")

    # STUDENT calling admin API -> 403 FORBIDDEN; ADMIN calling /register -> 403 FORBIDDEN
    assert (
        client.post(
            "/api/v1/admin/course-classes",
            headers=auth_headers(sv1["access_token"]),
            json={
                "class_code": "NOPE-01",
                "course_code": "CNNT",
                "course_name": "Test",
                "credits": 3,
                "capacity": 10,
                "status": "OPEN",
                "schedule": [],
                "prerequisite_course_codes": [],
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/register",
            headers=auth_headers(admin["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
            json={"student_id": "AD0001", "course_class_id": "LHP001"},
        ).status_code
        == 403
    )

    # Admin creates new class -> 201 LHP004; duplicate class_code -> 409 CLASS_CODE_EXISTS
    create_payload = {
        "class_code": "DB101-01",
        "course_code": "DB101",
        "course_name": "Cơ sở dữ liệu nâng cao",
        "credits": 4,
        "capacity": 2,
        "status": "OPEN",
        "schedule": [{"day_of_week": "WED", "start_period": 1, "end_period": 3, "room": "D401"}],
        "prerequisite_course_codes": ["CS101", "JAVA"],
    }
    r_c = client.post(
        "/api/v1/admin/course-classes",
        headers=auth_headers(admin["access_token"]),
        json=create_payload,
    )
    assert r_c.status_code == 201
    new_cid = r_c.json()["data"]["course_class"]["course_class_id"]
    assert new_cid == "LHP004"
    assert r_c.json()["data"]["course_class"]["tuition_amount"] == 2000000

    r_dup_code = client.post(
        "/api/v1/admin/course-classes",
        headers=auth_headers(admin["access_token"]),
        json=create_payload,
    )
    assert r_dup_code.status_code == 409
    assert r_dup_code.json()["code"] == "CLASS_CODE_EXISTS"

    # While 0 ACTIVE, admin can change credits/schedule/prereqs freely
    updated_zero_active = {
        **create_payload,
        "credits": 3,
        "prerequisite_course_codes": ["CS101"],
    }
    r_put0 = client.put(
        f"/api/v1/admin/course-classes/{new_cid}",
        headers=auth_headers(admin["access_token"]),
        json=updated_zero_active,
    )
    assert r_put0.status_code == 200
    assert r_put0.json()["data"]["course_class"]["tuition_amount"] == 1500000

    # SV0001 & SV0002 register on LHP003 (2 ACTIVE)
    for tok, sid in ((sv1, "SV0001"), (sv2, "SV0002")):
        assert (
            client.post(
                "/api/v1/register",
                headers=auth_headers(tok["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
                json={"student_id": sid, "course_class_id": "LHP003"},
            ).status_code
            == 200
        )

    # Reducing capacity to 1 (< 2 ACTIVE) -> 409 CAPACITY_BELOW_REGISTERED
    r_low_cap = client.put(
        "/api/v1/admin/course-classes/LHP003",
        headers=auth_headers(admin["access_token"]),
        json={
            "class_code": "JAVA-01",
            "course_code": "JAVA",
            "course_name": "Lập trình hướng đối tượng với Java",
            "credits": 3,
            "capacity": 1,
            "status": "OPEN",
            "schedule": [{"day_of_week": "TUE", "start_period": 1, "end_period": 3, "room": "C301"}],
            "prerequisite_course_codes": [],
        },
    )
    assert r_low_cap.status_code == 409
    assert r_low_cap.json()["code"] == "CAPACITY_BELOW_REGISTERED"

    # Changing schedule while ACTIVE > 0 -> 409 CLASS_HAS_REGISTRATIONS
    r_chg_sched = client.put(
        "/api/v1/admin/course-classes/LHP003",
        headers=auth_headers(admin["access_token"]),
        json={
            "class_code": "JAVA-01",
            "course_code": "JAVA",
            "course_name": "Lập trình hướng đối tượng với Java",
            "credits": 3,
            "capacity": 10,
            "status": "OPEN",
            "schedule": [{"day_of_week": "FRI", "start_period": 1, "end_period": 3, "room": "C301"}],
            "prerequisite_course_codes": [],
        },
    )
    assert r_chg_sched.status_code == 409
    assert r_chg_sched.json()["code"] == "CLASS_HAS_REGISTRATIONS"

    # Renaming course_name & changing capacity to 10 succeeds, AND existing registration snapshot keeps original course_name!
    r_rename = client.put(
        "/api/v1/admin/course-classes/LHP003",
        headers=auth_headers(admin["access_token"]),
        json={
            "class_code": "JAVA-01",
            "course_code": "JAVA",
            "course_name": "Tên lớp mới sau khi đã đăng ký",
            "credits": 3,
            "capacity": 10,
            "status": "OPEN",
            "schedule": [{"day_of_week": "TUE", "start_period": 1, "end_period": 3, "room": "C301"}],
            "prerequisite_course_codes": [],
        },
    )
    assert r_rename.status_code == 200
    assert r_rename.json()["data"]["course_class"]["remaining_seats"] == 8

    my_regs = client.get(
        "/api/v1/registrations/me",
        headers=auth_headers(sv1["access_token"]),
    ).json()["data"]["items"]
    assert my_regs[0]["course_name"] == "Lập trình hướng đối tượng với Java"


def test_tc19_tc20_refresh_rotation_absolute_ttl_logout_and_idempotency_reuse(
    client: TestClient,
) -> None:
    base_time = datetime(2026, 11, 1, 8, 0, 0, tzinfo=UTC)
    with Clock.override(base_time):
        dev1 = login_and_get_tokens(client, "SV0001")
        dev2 = login_and_get_tokens(client, "SV0001")

    # TC20: Register with key K1 -> replay with reordered JSON keys & refreshed token -> 422 on different body/path
    k1 = str(uuid.uuid4())
    with Clock.override(base_time + timedelta(minutes=5)):
        r_orig = client.post(
            "/api/v1/register",
            content=b'{"student_id":"SV0001","course_class_id":"LHP003"}',
            headers=auth_headers(
                dev1["access_token"],
                **{"Idempotency-Key": k1, "Content-Type": "application/json"},
            ),
        )
        assert r_orig.status_code == 200

        # TC19: Refresh dev1 session near 7.5 hours -> remaining absolute TTL is 1800s (NOT reset to 28800s!)
    with Clock.override(base_time + timedelta(hours=7, minutes=30)):
        r_ref = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": dev1["refresh_token"]},
        )
        assert r_ref.status_code == 200
        ref_data = r_ref.json()["data"]
        assert ref_data["expires_in"] == 1800
        assert ref_data["refresh_expires_in"] == 1800

        # Old refresh token is immediately invalid on 2nd attempt
        r_ref_old = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": dev1["refresh_token"]},
        )
        assert r_ref_old.status_code == 401
        assert r_ref_old.json()["code"] == "INVALID_REFRESH_TOKEN"

        # Old access token is also immediately invalid
        assert (
            client.get(
                "/api/v1/course-classes",
                headers=auth_headers(dev1["access_token"]),
            ).status_code
            == 401
        )

        # Replay K1 with NEW access token and REORDERED JSON keys -> 200 Idempotent-Replayed!
        r_reordered = client.post(
            "/api/v1/register",
            content=b'{"course_class_id":"LHP003","student_id":"SV0001"}',
            headers=auth_headers(
                ref_data["access_token"],
                **{"Idempotency-Key": k1, "Content-Type": "application/json"},
            ),
        )
        assert r_reordered.status_code == 200
        assert r_reordered.headers.get("Idempotent-Replayed") == "true"

        # Reusing K1 with different class_id -> 422 IDEMPOTENCY_KEY_REUSED
        r_422_body = client.post(
            "/api/v1/register",
            headers=auth_headers(ref_data["access_token"], **{"Idempotency-Key": k1}),
            json={"student_id": "SV0001", "course_class_id": "LHP001"},
        )
        assert r_422_body.status_code == 422
        assert r_422_body.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

        # Reusing K1 on DELETE endpoint -> 422 IDEMPOTENCY_KEY_REUSED
        reg_id = r_orig.json()["data"]["registration"]["registration_id"]
        r_422_method = client.delete(
            f"/api/v1/registrations/{reg_id}",
            headers=auth_headers(ref_data["access_token"], **{"Idempotency-Key": k1}),
        )
        assert r_422_method.status_code == 422
        assert r_422_method.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

        # Another student (SV0002) using the SAME UUID `k1` has independent user scope!
        sv2 = login_and_get_tokens(client, "SV0002")
        r_sv2_same_key = client.post(
            "/api/v1/register",
            headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": k1}),
            json={"student_id": "SV0002", "course_class_id": "LHP002"},
        )
        assert r_sv2_same_key.status_code == 200

        # Logout dev1 session -> revokes dev1, while dev2 (2nd device) remains active!
        # Trying logout with mismatched refresh token (dev2's refresh with dev1's access) -> 401
        r_bad_logout = client.post(
            "/api/v1/auth/logout",
            headers=auth_headers(ref_data["access_token"]),
            json={"refresh_token": dev2["refresh_token"]},
        )
        assert r_bad_logout.status_code == 401
        assert r_bad_logout.json()["code"] == "INVALID_REFRESH_TOKEN"

        r_ok_logout = client.post(
            "/api/v1/auth/logout",
            headers=auth_headers(ref_data["access_token"]),
            json={"refresh_token": ref_data["refresh_token"]},
        )
        assert r_ok_logout.status_code == 200
        assert r_ok_logout.json()["code"] == "LOGGED_OUT"

        # Revoked session rejected immediately
        assert (
            client.get(
                "/api/v1/course-classes",
                headers=auth_headers(ref_data["access_token"]),
            ).status_code
            == 401
        )
        # Second device's initial 1-hour access token expired at +1h, while its 8-hour session is NOT revoked!
        assert (
            client.get(
                "/api/v1/course-classes",
                headers=auth_headers(dev2["access_token"]),
            ).status_code
            == 401
        )
        r_dev2_ref = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": dev2["refresh_token"]},
        )
        assert r_dev2_ref.status_code == 200
        dev2_ref_data = r_dev2_ref.json()["data"]
        assert dev2_ref_data["expires_in"] == 1800
        assert (
            client.get(
                "/api/v1/course-classes",
                headers=auth_headers(dev2_ref_data["access_token"]),
            ).status_code
            == 200
        )

    # Past 8h absolute session cap -> dev2's rotated refresh token is rejected!
    with Clock.override(base_time + timedelta(hours=8, seconds=1)):
        r_abs_exp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": dev2_ref_data["refresh_token"]},
        )
        assert r_abs_exp.status_code == 401
        assert r_abs_exp.json()["code"] == "INVALID_REFRESH_TOKEN"


def test_tc21_redis_queue_fifo_expiry_logout_replay_and_fail_closed(
    clean_db: str,
    lua_redis: Any,
) -> None:
    settings = make_test_settings(
        clean_db,
        queue_enabled=True,
        queue_max_ready=1,
        queue_token_ttl_seconds=60,
    )
    app = create_app(settings=settings, redis_override=lua_redis)

    base_t = datetime(2026, 11, 1, 9, 0, 0, tzinfo=UTC)
    with Clock.override(base_t), TestClient(app, raise_server_exceptions=False) as tc:
        assert tc.get("/api/v1/health").json()["data"]["features"]["queue"] is True

        sv1 = login_and_get_tokens(tc, "SV0001")
        sv2 = login_and_get_tokens(tc, "SV0002")

        # Initial status is NONE (does NOT auto-join)
        st0 = tc.get("/api/v1/queue/status", headers=auth_headers(sv1["access_token"])).json()["data"]
        assert st0["status"] == "NONE"

        # Register without queue token -> 403 QUEUE_TOKEN_REQUIRED
        r_no_q = tc.post(
            "/api/v1/register",
            headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": str(uuid.uuid4())}),
            json={"student_id": "SV0001", "course_class_id": "LHP003"},
        )
        assert r_no_q.status_code == 403
        assert r_no_q.json()["code"] == "QUEUE_TOKEN_REQUIRED"

        # SV0001 joins -> gets READY (max_ready=1); SV0002 joins -> WAITING position=1
        j1 = tc.post("/api/v1/queue/join", headers=auth_headers(sv1["access_token"]), json={}).json()["data"]
        assert j1["status"] == "READY"
        q_tok_1 = j1["queue_token"]
        assert q_tok_1 is not None

        j2 = tc.post("/api/v1/queue/join", headers=auth_headers(sv2["access_token"]), json={}).json()["data"]
        assert j2["status"] == "WAITING"
        assert j2["position"] == 1
        assert j2["queue_token"] is None

        # SV0002 trying to use SV0001's queue token -> 403 QUEUE_TOKEN_INVALID
        r_steal = tc.post(
            "/api/v1/register",
            headers=auth_headers(
                sv2["access_token"],
                **{"Idempotency-Key": str(uuid.uuid4()), "X-Queue-Token": q_tok_1},
            ),
            json={"student_id": "SV0002", "course_class_id": "LHP003"},
        )
        assert r_steal.status_code == 403
        assert r_steal.json()["code"] == "QUEUE_TOKEN_INVALID"

        # SV0001 registers LHP001 & LHP003 reusing the same READY token before expiry!
        idem_sv1 = str(uuid.uuid4())
        r_ok1 = tc.post(
            "/api/v1/register",
            headers=auth_headers(
                sv1["access_token"],
                **{"Idempotency-Key": idem_sv1, "X-Queue-Token": q_tok_1},
            ),
            json={"student_id": "SV0001", "course_class_id": "LHP001"},
        )
        assert r_ok1.status_code == 200
        assert (
            tc.post(
                "/api/v1/register",
                headers=auth_headers(
                    sv1["access_token"],
                    **{"Idempotency-Key": str(uuid.uuid4()), "X-Queue-Token": q_tok_1},
                ),
                json={"student_id": "SV0001", "course_class_id": "LHP003"},
            ).status_code
            == 200
        )

        # Advance clock past 60s TTL -> SV0001 becomes EXPIRED, SV0002 is promoted to READY!
        with Clock.override(base_t + timedelta(seconds=65)):
            st_sv2 = tc.get("/api/v1/queue/status", headers=auth_headers(sv2["access_token"])).json()["data"]
            assert st_sv2["status"] == "READY"
            assert st_sv2["queue_token"] is not None

            st_sv1 = tc.get("/api/v1/queue/status", headers=auth_headers(sv1["access_token"])).json()["data"]
            assert st_sv1["status"] == "EXPIRED"

            # New register with expired token fails 403 QUEUE_TOKEN_INVALID
            r_exp = tc.post(
                "/api/v1/register",
                headers=auth_headers(
                    sv1["access_token"],
                    **{"Idempotency-Key": str(uuid.uuid4()), "X-Queue-Token": q_tok_1},
                ),
                json={"student_id": "SV0001", "course_class_id": "LHP002"},
            )
            assert r_exp.status_code == 403
            assert r_exp.json()["code"] == "QUEUE_TOKEN_INVALID"

            # BUT replay of already-COMMITted `idem_sv1` succeeds even without/expired queue token!
            r_replay_after_exp = tc.post(
                "/api/v1/register",
                headers=auth_headers(sv1["access_token"], **{"Idempotency-Key": idem_sv1}),
                json={"student_id": "SV0001", "course_class_id": "LHP001"},
            )
            assert r_replay_after_exp.status_code == 200
            assert r_replay_after_exp.headers.get("Idempotent-Replayed") == "true"

            # Logout SV0002 releases READY slot cleanly
            tc.post(
                "/api/v1/auth/logout",
                headers=auth_headers(sv2["access_token"]),
                json={"refresh_token": sv2["refresh_token"]},
            )

        # Simulate Redis outage -> fail closed 503 SERVICE_UNAVAILABLE (never bypasses queue!)
        app.state.queue_service.set_redis_client(None)
        assert tc.get("/api/v1/health").status_code == 503
        r_fail_closed = tc.post(
            "/api/v1/register",
            headers=auth_headers(
                sv1["access_token"],
                **{"Idempotency-Key": str(uuid.uuid4()), "X-Queue-Token": "any"},
            ),
            json={"student_id": "SV0001", "course_class_id": "LHP002"},
        )
        assert r_fail_closed.status_code == 503
        assert r_fail_closed.json()["code"] == "SERVICE_UNAVAILABLE"


def test_tc22_oidc_sso_pkce_rsa_jwt_verification_and_one_time_exchange(
    clean_db: str,
) -> None:
    # Generate real 2048-bit RSA keypair to sign & verify OIDC ID tokens with PyJWT
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    issuer = "http://localhost:8081/realms/dkhp"
    client_id = "dkhp-backend"

    settings = make_test_settings(
        clean_db,
        sso_enabled=True,
        oidc_issuer=issuer,
        oidc_client_id=client_id,
    )

    captured_nonce: dict[str, str] = {}

    def _token_exchanger(form_data: dict[str, str]) -> dict[str, Any]:
        assert form_data["grant_type"] == "authorization_code"
        assert len(form_data["code_verifier"]) >= 43
        now_ts = int(datetime.now(UTC).timestamp())
        id_token = jwt.encode(
            {
                "iss": issuer,
                "sub": KEYCLOAK_SV0001_SUB,
                "aud": client_id,
                "azp": client_id,
                "iat": now_ts,
                "exp": now_ts + 300,
                "nonce": captured_nonce["nonce"],
            },
            private_key,
            algorithm="RS256",
        )
        return {"id_token": id_token, "access_token": "kc-unused", "token_type": "Bearer"}

    def _id_token_verifier(raw_jwt: str) -> dict[str, Any]:
        return jwt.decode(
            raw_jwt,
            public_key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )

    app = create_app(settings=settings)
    with TestClient(app, raise_server_exceptions=False) as tc:
        # Wire RSA verifier into live SsoService
        auth_svc: AuthService = app.state.auth_service
        app.state.sso_service = SsoService(
            app.state.db,
            settings,
            auth_svc,
            token_exchanger=_token_exchanger,
            id_token_verifier=_id_token_verifier,
        )

        # 1. GET /auth/sso/login -> 302 to Keycloak with state, nonce, PKCE S256 + browser bind cookie
        r_login = tc.get("/api/v1/auth/sso/login", follow_redirects=False)
        assert r_login.status_code == 302
        loc = urlparse(r_login.headers["location"])
        qs = parse_qs(loc.query)
        state = qs["state"][0]
        captured_nonce["nonce"] = qs["nonce"][0]
        assert qs["code_challenge_method"] == ["S256"]
        bind_cookie = r_login.cookies.get(SSO_BIND_COOKIE_NAME)
        assert bind_cookie is not None

        # 2. Callback WITHOUT browser-binding cookie (Login CSRF attempt) fails safely!
        r_login_csrf = tc.get("/api/v1/auth/sso/login", follow_redirects=False)
        csrf_state = parse_qs(urlparse(r_login_csrf.headers["location"]).query)["state"][0]
        tc.cookies.clear()
        r_csrf_cb = tc.get(
            f"/api/v1/auth/sso/callback?code=authcode1&state={csrf_state}",
            follow_redirects=False,
        )
        assert r_csrf_cb.status_code == 302
        assert r_csrf_cb.headers["location"].endswith("/sso/callback?error=SSO_FAILED")

        # 3. Valid callback with matching browser-binding cookie -> 302 with one-time exchange_code
        tc.cookies.set(SSO_BIND_COOKIE_NAME, bind_cookie)
        r_cb = tc.get(
            f"/api/v1/auth/sso/callback?code=valid_kc_code&state={state}",
            follow_redirects=False,
        )
        assert r_cb.status_code == 302
        cb_qs = parse_qs(urlparse(r_cb.headers["location"]).query)
        exchange_code = cb_qs["exchange_code"][0]

        # Replaying the same `state` on callback fails -> ?error=SSO_FAILED
        tc.cookies.set(SSO_BIND_COOKIE_NAME, bind_cookie)
        r_cb_replay = tc.get(
            f"/api/v1/auth/sso/callback?code=valid_kc_code&state={state}",
            follow_redirects=False,
        )
        assert r_cb_replay.headers["location"].endswith("/sso/callback?error=SSO_FAILED")

        # 4. POST /auth/sso/exchange (cookie-free JSON call!) -> 200 LOGIN_SUCCESS for SV0001
        tc.cookies.clear()
        r_ex1 = tc.post("/api/v1/auth/sso/exchange", json={"exchange_code": exchange_code})
        assert r_ex1.status_code == 200
        ex_data = r_ex1.json()["data"]
        assert ex_data["student"]["student_id"] == "SV0001"
        assert ex_data["student"]["role"] == "STUDENT"

        # 5. Reusing exchange_code a second time -> 401 SSO_FAILED!
        r_ex2 = tc.post("/api/v1/auth/sso/exchange", json={"exchange_code": exchange_code})
        assert r_ex2.status_code == 401
        assert r_ex2.json()["code"] == "SSO_FAILED"
