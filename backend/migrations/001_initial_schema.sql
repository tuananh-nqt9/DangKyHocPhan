-- Migration 001: Initial schema for Online Course Registration System (DKHP)
-- Target DBMS: PostgreSQL 16
-- Enforces strict types, UTC TIMESTAMPTZ, partial unique index for ACTIVE registrations,
-- historical snapshots, session token hashes, transactional idempotency, and OIDC SSO tables.

CREATE SEQUENCE IF NOT EXISTS course_class_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 999999
    CACHE 1;

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    student_id VARCHAR(16) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    role VARCHAR(16) NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_users_student_id UNIQUE (student_id),
    CONSTRAINT chk_users_student_id_format CHECK (student_id ~ '^(SV|AD)[0-9]{3,6}$'),
    CONSTRAINT chk_users_full_name_nonempty CHECK (btrim(full_name) <> ''),
    CONSTRAINT chk_users_role CHECK (role IN ('STUDENT', 'ADMIN'))
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_token_hash CHAR(64) NOT NULL,
    refresh_token_hash CHAR(64) NOT NULL,
    access_expires_at TIMESTAMPTZ NOT NULL,
    refresh_expires_at TIMESTAMPTZ NOT NULL,
    absolute_expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rotated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_sessions_access_hash UNIQUE (access_token_hash),
    CONSTRAINT uq_sessions_refresh_hash UNIQUE (refresh_token_hash),
    CONSTRAINT chk_sessions_expiry_bounds CHECK (
        access_expires_at <= absolute_expires_at
        AND refresh_expires_at <= absolute_expires_at
    )
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id
    ON sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_sessions_active_expiry
    ON sessions(absolute_expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS courses (
    course_code VARCHAR(32) PRIMARY KEY,
    course_name VARCHAR(200) NOT NULL,
    default_credits INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_courses_code_nonempty CHECK (btrim(course_code) <> ''),
    CONSTRAINT chk_courses_name_nonempty CHECK (btrim(course_name) <> ''),
    CONSTRAINT chk_courses_default_credits CHECK (default_credits BETWEEN 1 AND 30)
);

CREATE TABLE IF NOT EXISTS course_completions (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_code VARCHAR(32) NOT NULL REFERENCES courses(course_code) ON DELETE RESTRICT,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, course_code)
);

CREATE INDEX IF NOT EXISTS idx_course_completions_user
    ON course_completions(user_id);

CREATE TABLE IF NOT EXISTS course_classes (
    course_class_id VARCHAR(16) PRIMARY KEY,
    class_code VARCHAR(32) NOT NULL,
    course_code VARCHAR(32) NOT NULL REFERENCES courses(course_code) ON DELETE RESTRICT,
    course_name VARCHAR(200) NOT NULL,
    credits INTEGER NOT NULL,
    capacity INTEGER NOT NULL,
    remaining_seats INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL,
    tuition_amount BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_course_classes_class_code UNIQUE (class_code),
    CONSTRAINT chk_course_classes_id_format CHECK (course_class_id ~ '^LHP[0-9]{3,6}$'),
    CONSTRAINT chk_course_classes_class_code_nonempty CHECK (btrim(class_code) <> ''),
    CONSTRAINT chk_course_classes_course_name_nonempty CHECK (btrim(course_name) <> ''),
    CONSTRAINT chk_course_classes_credits CHECK (credits BETWEEN 1 AND 30),
    CONSTRAINT chk_course_classes_capacity CHECK (capacity BETWEEN 1 AND 10000),
    CONSTRAINT chk_course_classes_remaining_seats CHECK (
        remaining_seats >= 0 AND remaining_seats <= capacity
    ),
    CONSTRAINT chk_course_classes_status CHECK (status IN ('OPEN', 'CLOSED')),
    CONSTRAINT chk_course_classes_tuition_amount CHECK (tuition_amount >= 0)
);

CREATE INDEX IF NOT EXISTS idx_course_classes_course_code
    ON course_classes(course_code);

CREATE INDEX IF NOT EXISTS idx_course_classes_status
    ON course_classes(status);

CREATE TABLE IF NOT EXISTS course_class_schedules (
    id BIGSERIAL PRIMARY KEY,
    course_class_id VARCHAR(16) NOT NULL REFERENCES course_classes(course_class_id) ON DELETE CASCADE,
    day_of_week VARCHAR(3) NOT NULL,
    start_period INTEGER NOT NULL,
    end_period INTEGER NOT NULL,
    room VARCHAR(100) NOT NULL,
    CONSTRAINT chk_schedule_day_of_week CHECK (
        day_of_week IN ('MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN')
    ),
    CONSTRAINT chk_schedule_periods CHECK (
        start_period BETWEEN 1 AND 12
        AND end_period BETWEEN 1 AND 12
        AND start_period <= end_period
    ),
    CONSTRAINT chk_schedule_room_nonempty CHECK (btrim(room) <> ''),
    CONSTRAINT uq_course_class_schedule_slot UNIQUE (
        course_class_id, day_of_week, start_period, end_period, room
    )
);

CREATE INDEX IF NOT EXISTS idx_course_class_schedules_class
    ON course_class_schedules(course_class_id, id);

CREATE TABLE IF NOT EXISTS course_class_prerequisites (
    course_class_id VARCHAR(16) NOT NULL REFERENCES course_classes(course_class_id) ON DELETE CASCADE,
    prerequisite_course_code VARCHAR(32) NOT NULL REFERENCES courses(course_code) ON DELETE RESTRICT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (course_class_id, prerequisite_course_code)
);

CREATE INDEX IF NOT EXISTS idx_course_class_prerequisites_order
    ON course_class_prerequisites(course_class_id, sort_order, prerequisite_course_code);

CREATE TABLE IF NOT EXISTS registrations (
    registration_id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    student_id VARCHAR(16) NOT NULL,
    course_class_id VARCHAR(16) NOT NULL REFERENCES course_classes(course_class_id) ON DELETE RESTRICT,
    class_code VARCHAR(32) NOT NULL,
    course_name VARCHAR(200) NOT NULL,
    credits INTEGER NOT NULL,
    tuition_amount BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL,
    payment_status VARCHAR(16) NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at TIMESTAMPTZ NULL,
    CONSTRAINT chk_registrations_credits CHECK (credits BETWEEN 1 AND 30),
    CONSTRAINT chk_registrations_tuition CHECK (tuition_amount >= 0),
    CONSTRAINT chk_registrations_status CHECK (status IN ('ACTIVE', 'CANCELLED')),
    CONSTRAINT chk_registrations_payment_status CHECK (
        payment_status IN ('UNPAID', 'PAID', 'REFUNDED')
    ),
    CONSTRAINT chk_registrations_state_consistency CHECK (
        (
            status = 'ACTIVE'
            AND cancelled_at IS NULL
            AND payment_status IN ('UNPAID', 'PAID')
        )
        OR (
            status = 'CANCELLED'
            AND cancelled_at IS NOT NULL
            AND cancelled_at >= registered_at
            AND payment_status IN ('UNPAID', 'REFUNDED')
        )
    )
);

-- Critical partial unique constraint: at most one ACTIVE registration per (user, class),
-- while allowing historical CANCELLED rows and subsequent re-registration with a new UUID.
CREATE UNIQUE INDEX IF NOT EXISTS uq_registrations_active_user_class
    ON registrations(user_id, course_class_id)
    WHERE status = 'ACTIVE';

CREATE INDEX IF NOT EXISTS idx_registrations_user_history
    ON registrations(user_id, registered_at DESC, registration_id ASC);

CREATE INDEX IF NOT EXISTS idx_registrations_user_status_history
    ON registrations(user_id, status, registered_at DESC, registration_id ASC);

CREATE INDEX IF NOT EXISTS idx_registrations_active_class
    ON registrations(course_class_id)
    WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS payments (
    payment_id UUID PRIMARY KEY,
    registration_id UUID NOT NULL REFERENCES registrations(registration_id) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    course_class_id VARCHAR(16) NOT NULL REFERENCES course_classes(course_class_id) ON DELETE RESTRICT,
    class_code VARCHAR(32) NOT NULL,
    amount BIGINT NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'VND',
    status VARCHAR(16) NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    refunded_at TIMESTAMPTZ NULL,
    CONSTRAINT uq_payments_registration_id UNIQUE (registration_id),
    CONSTRAINT chk_payments_amount CHECK (amount >= 0),
    CONSTRAINT chk_payments_currency CHECK (currency = 'VND'),
    CONSTRAINT chk_payments_status CHECK (status IN ('PAID', 'REFUNDED')),
    CONSTRAINT chk_payments_refund_consistency CHECK (
        (status = 'PAID' AND refunded_at IS NULL)
        OR (status = 'REFUNDED' AND refunded_at IS NOT NULL AND refunded_at >= paid_at)
    )
);

CREATE INDEX IF NOT EXISTS idx_payments_user_history
    ON payments(user_id, paid_at DESC, payment_id ASC);

CREATE INDEX IF NOT EXISTS idx_payments_user_status_history
    ON payments(user_id, status, paid_at DESC, payment_id ASC);

CREATE TABLE IF NOT EXISTS idempotency_records (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    idempotency_key UUID NOT NULL,
    request_method VARCHAR(16) NOT NULL,
    request_path VARCHAR(255) NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    response_status INTEGER NOT NULL,
    response_code VARCHAR(64) NOT NULL,
    response_body JSONB NOT NULL,
    original_request_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_idempotency_user_key UNIQUE (user_id, idempotency_key),
    CONSTRAINT chk_idempotency_expiry CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_idempotency_expires_at
    ON idempotency_records(expires_at);

CREATE TABLE IF NOT EXISTS sso_identities (
    id BIGSERIAL PRIMARY KEY,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_sso_issuer_subject UNIQUE (issuer, subject),
    CONSTRAINT uq_sso_issuer_user UNIQUE (issuer, user_id)
);

CREATE TABLE IF NOT EXISTS sso_transactions (
    state VARCHAR(128) PRIMARY KEY,
    nonce VARCHAR(128) NOT NULL,
    code_verifier VARCHAR(128) NOT NULL,
    browser_bind_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_sso_transactions_expires_at
    ON sso_transactions(expires_at);

CREATE TABLE IF NOT EXISTS sso_exchange_codes (
    code_hash CHAR(64) PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_sso_exchange_codes_expires_at
    ON sso_exchange_codes(expires_at);
