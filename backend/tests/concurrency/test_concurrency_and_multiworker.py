"""True multi-connection & multi-worker (2 OS processes) concurrency tests (TC06, TC07, TC23, TC24, TC25)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from app.main import create_app
from app.services.idempotency_service import FaultHooks
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from scripts.check_invariants import run_invariant_checks
from scripts.prepare_tokens import prepare_student_tokens
from scripts.seed import LAB_DEMO_PASSWORD
from tests.conftest import auth_headers, login_and_get_tokens, make_test_settings

pytestmark = pytest.mark.concurrency

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def multiworker_server_url(
    test_db_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[str]:
    """Launch a REAL 2-worker Uvicorn HTTP server (`--workers 2`) against PostgreSQL 16."""
    port = _find_free_port()
    log_dir = tmp_path_factory.mktemp("uvicorn_mw")
    log_path = log_dir / "uvicorn_multiworker.log"
    log_handle = log_path.open("w", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "APP_ENV": "test",
            "DATABASE_URL": test_db_url,
            "TEST_DATABASE_URL": test_db_url,
            "DB_POOL_MIN_SIZE": "2",
            "DB_POOL_MAX_SIZE": "15",
            "DB_POOL_TIMEOUT_SECONDS": "10.0",
            "DB_LOCK_TIMEOUT_MS": "5000",
            "DB_IDEMPOTENCY_LOCK_TIMEOUT_MS": "600",
            "DB_STATEMENT_TIMEOUT_MS": "10000",
            "PAYMENTS_ENABLED": "true",
            "SSO_ENABLED": "false",
            "QUEUE_ENABLED": "false",
            "RATE_LIMIT_BACKEND": "none",
            "LOG_LEVEL": "INFO",
        }
    )

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "2",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )

    base_url = f"http://127.0.0.1:{port}"
    ready = False
    deadline = time.monotonic() + 25.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log_handle.flush()
            log_out = log_path.read_text(encoding="utf-8", errors="replace")
            log_handle.close()
            raise RuntimeError(f"2-worker Uvicorn exited prematurely:\n{log_out}")
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            both_workers_started = log_text.count("Application startup complete.") >= 2
            if both_workers_started:
                r = httpx.get(f"{base_url}/api/v1/health", timeout=2.0)
                if r.status_code == 200:
                    ready = True
                    break
        except httpx.HTTPError:
            pass
        time.sleep(0.2)

    if not ready:
        proc.terminate()
        log_handle.close()
        log_out = log_path.read_text(encoding="utf-8", errors="replace")
        raise RuntimeError(f"Timed out waiting for 2-worker Uvicorn server readiness:\n{log_out}")

    try:
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_handle.close()


def test_tc06_20_students_compete_for_last_1_seat_across_2_workers(
    clean_db: str,
    multiworker_server_url: str,
    tmp_path: Path,
) -> None:
    # Prepare 1-seat class without prerequisites/schedules (per Spec Section 23)
    with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as admin_http:
        adm_tok = admin_http.post(
            "/api/v1/auth/login",
            json={"student_id": "AD0001", "password": LAB_DEMO_PASSWORD},
        ).json()["data"]["access_token"]

        c_resp = admin_http.post(
            "/api/v1/admin/course-classes",
            headers=auth_headers(adm_tok),
            json={
                "class_code": "RACE-TC06-01",
                "course_code": "JAVA",
                "course_name": "Tranh 1 chỗ cuối bởi 20 SV",
                "credits": 3,
                "capacity": 1,
                "status": "OPEN",
                "schedule": [],
                "prerequisite_course_codes": [],
            },
        )
        assert c_resp.status_code == 201
        target_cid = c_resp.json()["data"]["course_class"]["course_class_id"]

    # Pre-generate tokens for SV0001..SV0020 so Argon2 login doesn't skew arrival barrier
    tok_file = tmp_path / "tc06_tokens.json"
    prepare_student_tokens(clean_db, count=20, output_path=tok_file)
    import json

    tokens_list = json.loads(tok_file.read_text(encoding="utf-8"))["tokens"]

    barrier = threading.Barrier(20)

    def _fire(entry: dict[str, Any]) -> tuple[int, str, str]:
        idem_key = str(uuid.uuid4())
        with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
            barrier.wait(timeout=10.0)
            resp = hc.post(
                "/api/v1/register",
                headers=auth_headers(entry["access_token"], **{"Idempotency-Key": idem_key}),
                json={"student_id": entry["student_id"], "course_class_id": target_cid},
            )
            b = resp.json()
            return resp.status_code, str(b["code"]), str(b["request_id"])

    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(_fire, tokens_list))

    # Zero infrastructure errors allowed (no 5xx, no 429)
    infra_errors = [o for o in outcomes if o[0] not in (200, 409)]
    assert infra_errors == [], f"Unexpected infra errors in TC06: {infra_errors}"

    registered = [o for o in outcomes if o[0] == 200 and o[1] == "REGISTERED"]
    class_full = [o for o in outcomes if o[0] == 409 and o[1] == "CLASS_FULL"]
    assert len(registered) == 1
    assert len(class_full) == 19

    # Verify committed PostgreSQL state on a fresh connection
    with psycopg.connect(clean_db, row_factory=dict_row) as conn:
        cc = conn.execute(
            "SELECT capacity, remaining_seats FROM course_classes WHERE course_class_id = %s",
            (target_cid,),
        ).fetchone()
        active_cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM registrations WHERE course_class_id = %s AND status = 'ACTIVE'",
            (target_cid,),
        ).fetchone()["c"]
        assert cc == {"capacity": 1, "remaining_seats": 0}
        assert active_cnt == 1


def test_tc07_1_student_20_different_keys_concurrent_across_2_workers(
    clean_db: str,
    multiworker_server_url: str,
) -> None:
    with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
        sv1_tok = hc.post(
            "/api/v1/auth/login",
            json={"student_id": "SV0001", "password": LAB_DEMO_PASSWORD},
        ).json()["data"]["access_token"]

    barrier = threading.Barrier(20)

    def _fire(_idx: int) -> tuple[int, str]:
        with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
            barrier.wait(timeout=10.0)
            resp = hc.post(
                "/api/v1/register",
                headers=auth_headers(sv1_tok, **{"Idempotency-Key": str(uuid.uuid4())}),
                json={"student_id": "SV0001", "course_class_id": "LHP003"},
            )
            return resp.status_code, str(resp.json()["code"])

    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(_fire, range(20)))

    infra_errors = [o for o in outcomes if o[0] not in (200, 409)]
    assert infra_errors == [], f"Unexpected infra errors in TC07: {infra_errors}"

    registered = [o for o in outcomes if o == (200, "REGISTERED")]
    duplicates = [o for o in outcomes if o == (409, "ALREADY_REGISTERED")]
    assert len(registered) == 1
    assert len(duplicates) == 19

    with psycopg.connect(clean_db, row_factory=dict_row) as conn:
        rem = conn.execute(
            "SELECT remaining_seats FROM course_classes WHERE course_class_id = 'LHP003'"
        ).fetchone()["remaining_seats"]
        active_cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM registrations WHERE course_class_id = 'LHP003' AND status = 'ACTIVE'"
        ).fetchone()["c"]
        assert rem == 49
        assert active_cnt == 1


def test_tc23_same_student_concurrently_registers_two_overlapping_classes(
    clean_db: str,
    multiworker_server_url: str,
) -> None:
    # LHP001 (MON 1-3, prereq CS101 met by SV0001) overlaps LHP002 (MON 2-4)!
    with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
        sv1_tok = hc.post(
            "/api/v1/auth/login",
            json={"student_id": "SV0001", "password": LAB_DEMO_PASSWORD},
        ).json()["data"]["access_token"]

    barrier = threading.Barrier(2)

    def _register_class(cid: str) -> tuple[int, str]:
        with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
            barrier.wait(timeout=10.0)
            resp = hc.post(
                "/api/v1/register",
                headers=auth_headers(sv1_tok, **{"Idempotency-Key": str(uuid.uuid4())}),
                json={"student_id": "SV0001", "course_class_id": cid},
            )
            return resp.status_code, str(resp.json()["code"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(_register_class, ["LHP001", "LHP002"]))

    codes = sorted(o[1] for o in outcomes)
    assert codes == ["REGISTERED", "SCHEDULE_CONFLICT"], f"Unexpected TC23 outcomes: {outcomes}"

    inv = run_invariant_checks(clean_db)
    assert inv["ok"]
    assert inv["stats"]["active_registrations"] == 1


def test_tc24_concurrent_payment_and_cancellation_never_leaves_cancelled_paid(
    clean_db: str,
    multiworker_server_url: str,
) -> None:
    with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
        sv1_tok = hc.post(
            "/api/v1/auth/login",
            json={"student_id": "SV0001", "password": LAB_DEMO_PASSWORD},
        ).json()["data"]["access_token"]

    # Run 5 independent race rounds on LHP003 (register -> race pay vs cancel)
    for _round in range(5):
        with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
            reg_id = hc.post(
                "/api/v1/register",
                headers=auth_headers(sv1_tok, **{"Idempotency-Key": str(uuid.uuid4())}),
                json={"student_id": "SV0001", "course_class_id": "LHP003"},
            ).json()["data"]["registration"]["registration_id"]

        barrier = threading.Barrier(2)

        def _pay(rid: str = reg_id, bar: threading.Barrier = barrier) -> tuple[int, dict[str, Any]]:
            with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
                bar.wait(timeout=10.0)
                r = hc.post(
                    "/api/v1/payments",
                    headers=auth_headers(sv1_tok, **{"Idempotency-Key": str(uuid.uuid4())}),
                    json={"registration_id": rid},
                )
                return r.status_code, r.json()

        def _cancel(rid: str = reg_id, bar: threading.Barrier = barrier) -> tuple[int, dict[str, Any]]:
            with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
                bar.wait(timeout=10.0)
                r = hc.delete(
                    f"/api/v1/registrations/{rid}",
                    headers=auth_headers(sv1_tok, **{"Idempotency-Key": str(uuid.uuid4())}),
                )
                return r.status_code, r.json()

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_pay = pool.submit(_pay)
            f_can = pool.submit(_cancel)
            pay_status, pay_body = f_pay.result()
            can_status, can_body = f_can.result()

        assert can_status == 200
        assert can_body["code"] == "REGISTRATION_CANCELLED"

        if pay_status == 200:
            # Payment ran first -> cancellation MUST have refunded it!
            assert can_body["data"]["registration"]["payment_status"] == "REFUNDED"
            assert can_body["data"]["refund"]["status"] == "REFUNDED"
        else:
            # Cancellation ran first -> payment MUST receive 404 REGISTRATION_NOT_FOUND!
            assert pay_status == 404
            assert pay_body["code"] == "REGISTRATION_NOT_FOUND"
            assert can_body["data"]["registration"]["payment_status"] == "UNPAID"
            assert can_body["data"]["refund"] is None

    inv = run_invariant_checks(clean_db)
    assert inv["ok"], inv
    assert inv["stats"]["active_registrations"] == 0
    assert inv["stats"]["paid_payments"] == 0


def test_tc25_concurrent_same_key_in_progress_409_and_disconnect_after_commit(
    clean_db: str,
    multiworker_server_url: str,
) -> None:
    # Part A: 10 concurrent requests with the EXACT SAME Idempotency-Key across 2 OS workers
    with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
        sv1_tok = hc.post(
            "/api/v1/auth/login",
            json={"student_id": "SV0001", "password": LAB_DEMO_PASSWORD},
        ).json()["data"]["access_token"]

    shared_key = str(uuid.uuid4())
    barrier = threading.Barrier(10)

    def _send_same_key(_i: int) -> tuple[int, dict[str, Any], dict[str, str]]:
        with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
            barrier.wait(timeout=10.0)
            r = hc.post(
                "/api/v1/register",
                headers=auth_headers(sv1_tok, **{"Idempotency-Key": shared_key}),
                json={"student_id": "SV0001", "course_class_id": "LHP003"},
            )
            return r.status_code, r.json(), dict(r.headers)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_send_same_key, range(10)))

    ok_200 = [r for r in results if r[0] == 200]
    in_prog_409 = [r for r in results if r[0] == 409]
    assert len(ok_200) + len(in_prog_409) == 10
    assert len(ok_200) >= 1
    orig_req_ids = {r[1]["request_id"] for r in ok_200}
    assert len(orig_req_ids) == 1  # Every 200 response shares the exact original request_id!
    for r in in_prog_409:
        assert r[1]["code"] == "REQUEST_IN_PROGRESS"
        assert "retry-after" in {k.lower() for k in r[2]}

    # Part B: Deterministic slow hold (`REQUEST_IN_PROGRESS`) + simulated disconnect after COMMIT
    settings = make_test_settings(clean_db, db_idempotency_lock_timeout_ms=120)
    app = create_app(settings=settings)
    entered_tx = threading.Event()
    release_tx = threading.Event()

    def _hold_in_tx() -> None:
        entered_tx.set()
        release_tx.wait(timeout=3.0)

    def _drop_after_commit() -> None:
        raise ConnectionError("Simulated disconnect right after COMMIT")

    with TestClient(app, raise_server_exceptions=False) as tc:
        sv2 = login_and_get_tokens(tc, "SV0002")
        slow_key = str(uuid.uuid4())
        FaultHooks.in_transaction_hold = _hold_in_tx
        FaultHooks.after_commit_before_response = _drop_after_commit

        def _req1() -> int:
            r1 = tc.post(
                "/api/v1/register",
                headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": slow_key}),
                json={"student_id": "SV0002", "course_class_id": "LHP002"},
            )
            return r1.status_code

        with ThreadPoolExecutor(max_workers=1) as ex:
            fut1 = ex.submit(_req1)
            assert entered_tx.wait(timeout=3.0)

            # While req1 holds the advisory lock past 120ms, req2 deterministically gets 409 REQUEST_IN_PROGRESS!
            r2_while_busy = tc.post(
                "/api/v1/register",
                headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": slow_key}),
                json={"student_id": "SV0002", "course_class_id": "LHP002"},
            )
            assert r2_while_busy.status_code == 409
            assert r2_while_busy.json()["code"] == "REQUEST_IN_PROGRESS"
            assert r2_while_busy.headers["Retry-After"] == "1"

            release_tx.set()
            assert fut1.result() == 500  # req1 dropped after COMMIT!

        FaultHooks.reset()

        # Retry with `slow_key` recovers the exact committed result without writing twice!
        r_recovered = tc.post(
            "/api/v1/register",
            headers=auth_headers(sv2["access_token"], **{"Idempotency-Key": slow_key}),
            json={"student_id": "SV0002", "course_class_id": "LHP002"},
        )
        assert r_recovered.status_code == 200
        assert r_recovered.headers.get("Idempotent-Replayed") == "true"
        assert r_recovered.json()["data"]["course_class"]["remaining_seats"] == 49


def test_concurrent_refresh_and_admin_capacity_vs_register_across_2_workers(
    clean_db: str,
    multiworker_server_url: str,
) -> None:
    # 1. 6 concurrent refresh attempts on the same refresh_token -> exact 1 200 + 5 401!
    with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
        login_data = hc.post(
            "/api/v1/auth/login",
            json={"student_id": "SV0003", "password": LAB_DEMO_PASSWORD},
        ).json()["data"]
        adm_tok = hc.post(
            "/api/v1/auth/login",
            json={"student_id": "AD0001", "password": LAB_DEMO_PASSWORD},
        ).json()["data"]["access_token"]
        sv4_tok = hc.post(
            "/api/v1/auth/login",
            json={"student_id": "SV0004", "password": LAB_DEMO_PASSWORD},
        ).json()["data"]["access_token"]

    shared_rt = login_data["refresh_token"]
    ref_barrier = threading.Barrier(6)

    def _do_refresh(_i: int) -> int:
        with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
            ref_barrier.wait(timeout=10.0)
            return hc.post("/api/v1/auth/refresh", json={"refresh_token": shared_rt}).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        ref_statuses = list(pool.map(_do_refresh, range(6)))

    assert sorted(ref_statuses) == [200, 401, 401, 401, 401, 401]

    # 2. Admin PUT capacity update concurrently with Student POST /register -> seat invariant holds!
    adm_barrier = threading.Barrier(2)

    def _admin_put() -> int:
        with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
            adm_barrier.wait(timeout=10.0)
            return hc.put(
                "/api/v1/admin/course-classes/LHP002",
                headers=auth_headers(adm_tok),
                json={
                    "class_code": "WEB-01",
                    "course_code": "WEB",
                    "course_name": "Phát triển ứng dụng Web",
                    "credits": 3,
                    "capacity": 20,
                    "status": "OPEN",
                    "schedule": [
                        {"day_of_week": "MON", "start_period": 2, "end_period": 4, "room": "B201"}
                    ],
                    "prerequisite_course_codes": [],
                },
            ).status_code

    def _student_reg() -> int:
        with httpx.Client(base_url=multiworker_server_url, timeout=10.0) as hc:
            adm_barrier.wait(timeout=10.0)
            return hc.post(
                "/api/v1/register",
                headers=auth_headers(sv4_tok, **{"Idempotency-Key": str(uuid.uuid4())}),
                json={"student_id": "SV0004", "course_class_id": "LHP002"},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        s_adm = pool.submit(_admin_put)
        s_stu = pool.submit(_student_reg)
        assert s_adm.result() == 200
        assert s_stu.result() == 200

    inv = run_invariant_checks(clean_db)
    assert inv["ok"], inv
