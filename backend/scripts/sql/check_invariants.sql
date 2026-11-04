-- Reusable PostgreSQL 16 Data Integrity & Invariant Verification Queries (TV1 / TV2 / TV3)
-- Uses LEFT JOIN from `course_classes` so classes with 0 registrations are always verified.

-- 1. Seat conservation invariant: remaining_seats + COUNT(ACTIVE) = capacity AND 0 <= remaining_seats <= capacity
SELECT
    cc.course_class_id,
    cc.class_code,
    cc.capacity,
    cc.remaining_seats,
    COUNT(r.registration_id) AS active_count,
    (cc.remaining_seats + COUNT(r.registration_id)) AS computed_total
FROM course_classes cc
LEFT JOIN registrations r
    ON r.course_class_id = cc.course_class_id
   AND r.status = 'ACTIVE'
GROUP BY cc.course_class_id, cc.class_code, cc.capacity, cc.remaining_seats
HAVING cc.remaining_seats < 0
    OR COUNT(r.registration_id) > cc.capacity
    OR (cc.remaining_seats + COUNT(r.registration_id)) <> cc.capacity;

-- 2. No duplicate ACTIVE registrations on (user_id, course_class_id)
SELECT
    user_id,
    course_class_id,
    COUNT(*) AS duplicate_active_count
FROM registrations
WHERE status = 'ACTIVE'
GROUP BY user_id, course_class_id
HAVING COUNT(*) > 1;

-- 3. No CANCELLED registration may retain PAID status in registrations or payments
SELECT
    r.registration_id,
    r.status AS registration_status,
    r.payment_status AS registration_payment_status,
    p.payment_id,
    p.status AS payment_row_status
FROM registrations r
LEFT JOIN payments p ON p.registration_id = r.registration_id
WHERE r.status = 'CANCELLED'
  AND (r.payment_status = 'PAID' OR p.status = 'PAID');

-- 4. Every PAID registration must have an exact matching PAID payment row; REFUNDED must match REFUNDED
SELECT
    r.registration_id,
    r.status AS registration_status,
    r.payment_status,
    r.tuition_amount,
    p.payment_id,
    p.status AS payment_row_status,
    p.amount
FROM registrations r
LEFT JOIN payments p ON p.registration_id = r.registration_id
WHERE (r.payment_status = 'PAID' AND (p.payment_id IS NULL OR p.status <> 'PAID' OR p.amount <> r.tuition_amount))
   OR (r.payment_status = 'REFUNDED' AND (p.payment_id IS NULL OR p.status <> 'REFUNDED' OR p.amount <> r.tuition_amount))
   OR (r.payment_status = 'UNPAID' AND p.payment_id IS NOT NULL);

-- 5. No student may hold two distinct ACTIVE registrations with overlapping schedules
SELECT
    r1.user_id,
    r1.student_id,
    r1.course_class_id AS class_1,
    r2.course_class_id AS class_2,
    s1.day_of_week,
    GREATEST(s1.start_period, s2.start_period) AS overlap_start,
    LEAST(s1.end_period, s2.end_period) AS overlap_end
FROM registrations r1
JOIN registrations r2
    ON r1.user_id = r2.user_id
   AND r1.registration_id < r2.registration_id
   AND r1.status = 'ACTIVE'
   AND r2.status = 'ACTIVE'
JOIN course_class_schedules s1 ON s1.course_class_id = r1.course_class_id
JOIN course_class_schedules s2 ON s2.course_class_id = r2.course_class_id
WHERE s1.day_of_week = s2.day_of_week
  AND GREATEST(s1.start_period, s2.start_period) <= LEAST(s1.end_period, s2.end_period);
