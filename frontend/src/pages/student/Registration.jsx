import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, ArrowLeft, BookOpen, RefreshCw, X } from 'lucide-react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import DashboardLayout from '../../components/common/DashboardLayout.jsx';
import CourseDetailModal from '../../components/student/registration/CourseDetailModal.jsx';
import CourseList from '../../components/student/registration/CourseList.jsx';
import CourseSearch from '../../components/student/registration/CourseSearch.jsx';
import QueueStatus from '../../components/student/registration/QueueStatus.jsx';
import RegistrationConfirmModal from '../../components/student/registration/RegistrationConfirmModal.jsx';
import RegistrationResult from '../../components/student/registration/RegistrationResult.jsx';
import { getHealth } from '../../services/healthService.js';
import { getCourseClass, getCourseClasses } from '../../services/courseService.js';
import {
  cancelRegistration,
  getMyRegistrations,
  registerCourseClass,
} from '../../services/registrationService.js';
import { getQueueStatus, joinQueue, saveQueueState } from '../../services/queueService.js';
import { getCurrentUser } from '../../services/authService.js';
import { createIdempotencyKey } from '../../utils/idempotency.js';

const QUEUE_POLL_INTERVAL_MS = 3000;

const registrationMessages = {
  CLASS_FULL: 'Lớp học phần đã hết chỗ.',
  PREREQUISITE_NOT_MET: 'Bạn chưa hoàn thành môn học tiên quyết.',
  SCHEDULE_CONFLICT: 'Lịch học của lớp này bị trùng với học phần bạn đã đăng ký.',
  ALREADY_REGISTERED: 'Bạn đã đăng ký lớp học phần này.',
  REQUEST_IN_PROGRESS: 'Yêu cầu đăng ký đang được xử lý. Vui lòng chờ và thử lại.',
  SERVICE_BUSY: 'Hệ thống đang bận, vui lòng thử lại sau.',
  REGISTRATION_CLOSED: 'Lớp học phần đã đóng đăng ký.',
  QUEUE_TOKEN_INVALID: 'Lượt đăng ký đã hết hạn. Vui lòng cập nhật hoặc tham gia lại hàng đợi.',
  QUEUE_TOKEN_REQUIRED: 'Bạn cần tham gia hàng đợi và chờ đến lượt trước khi đăng ký.',
  RATE_LIMITED: 'Bạn đã gửi yêu cầu quá nhanh. Vui lòng chờ một lát rồi thử lại.',
  SERVICE_UNAVAILABLE: 'Dịch vụ tạm thời không khả dụng. Vui lòng thử lại sau.',
};

function getApiErrorMessage(error, fallback) {
  const apiError = error.response?.data;
  if (apiError?.code && registrationMessages[apiError.code]) {
    return registrationMessages[apiError.code];
  }
  if (error.code === 'ECONNABORTED' || error.code === 'ERR_NETWORK') {
    return 'Không nhận được phản hồi từ máy chủ. Bạn có thể thử lại; hệ thống sẽ giữ nguyên Idempotency-Key và dữ liệu yêu cầu.';
  }
  return apiError?.message || error.message || fallback;
}

function shouldKeepAttempt(error) {
  const code = error.response?.data?.code;
  return (
    !error.response ||
    error.code === 'ECONNABORTED' ||
    code === 'REQUEST_IN_PROGRESS' ||
    code === 'SERVICE_BUSY' ||
    code === 'RATE_LIMITED' ||
    code === 'SERVICE_UNAVAILABLE'
  );
}

function schedulesOverlap(firstSchedule = [], secondSchedule = []) {
  return firstSchedule.some((first) =>
    secondSchedule.some((second) =>
      first.day_of_week === second.day_of_week &&
      Number(first.start_period) <= Number(second.end_period) &&
      Number(second.start_period) <= Number(first.end_period),
    ),
  );
}

export default function StudentRegistration() {
  const [courses, setCourses] = useState([]);
  const [coursesLoading, setCoursesLoading] = useState(true);
  const [coursesError, setCoursesError] = useState('');
  const [featuresLoading, setFeaturesLoading] = useState(true);
  const [featuresError, setFeaturesError] = useState('');
  const [queueEnabled, setQueueEnabled] = useState(null);
  const [queueState, setQueueState] = useState(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueError, setQueueError] = useState('');
  const [queuePolling, setQueuePolling] = useState(false);
  const [search, setSearch] = useState('');
  const [detailSelection, setDetailSelection] = useState(null);
  const [detailCourse, setDetailCourse] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [confirmCourses, setConfirmCourses] = useState([]);
  const [registeringIds, setRegisteringIds] = useState(() => new Set());
  const [registrationResults, setRegistrationResults] = useState([]);
  const [batchProcessing, setBatchProcessing] = useState(false);
  const [activeRegistrations, setActiveRegistrations] = useState([]);
  const [registrationsError, setRegistrationsError] = useState('');
  const [cancelSelection, setCancelSelection] = useState(null);
  const [cancellingIds, setCancellingIds] = useState(() => new Set());
  const [cancelFeedback, setCancelFeedback] = useState(null);
  const [refreshError, setRefreshError] = useState('');
  const pendingAttempts = useRef(new Map());
  const pendingCancelAttempts = useRef(new Map());

  const loadCourses = useCallback(async () => {
    setCoursesLoading(true);
    setCoursesError('');
    try {
      const firstPage = await getCourseClasses({ page: 1, pageSize: 100 });
      const firstData = firstPage?.data;
      if (!Array.isArray(firstData?.items)) {
        throw new Error('Dữ liệu danh sách lớp học phần không hợp lệ.');
      }
      const allCourses = [...firstData.items];
      const totalPages = firstData?.pagination?.total_pages;

      if (!Number.isInteger(totalPages) || totalPages < 0) {
        throw new Error('Dữ liệu phân trang lớp học phần không hợp lệ.');
      }

      for (let page = 2; page <= totalPages; page += 1) {
        const response = await getCourseClasses({ page, pageSize: 100 });
        const items = response?.data?.items;
        if (!Array.isArray(items)) {
          throw new Error('Dữ liệu danh sách lớp học phần không hợp lệ.');
        }
        allCourses.push(...items);
      }

      setCourses(allCourses);
      return true;
    } catch (error) {
      setCoursesError(error.response?.data?.message || error.message || 'Không thể tải danh sách lớp học phần.');
      return false;
    } finally {
      setCoursesLoading(false);
    }
  }, []);

  const loadFeatures = useCallback(async () => {
    setFeaturesLoading(true);
    setFeaturesError('');
    setQueueEnabled(null);
    try {
      const response = await getHealth();
      const enabled = response?.data?.features?.queue;
      if (typeof enabled !== 'boolean') {
        throw new Error('Phản hồi trạng thái tính năng từ máy chủ không hợp lệ.');
      }
      setQueueEnabled(enabled);
      if (enabled) {
        const queueResponse = await getQueueStatus();
        const currentQueue = queueResponse?.data;
        setQueueState(currentQueue);
        saveQueueState(currentQueue);
      } else {
        setQueueState(null);
        saveQueueState(null);
      }
    } catch (error) {
      setFeaturesError(error.response?.data?.message || error.message || 'Không thể kiểm tra trạng thái hàng đợi.');
    } finally {
      setFeaturesLoading(false);
    }
  }, []);

  const refreshActiveRegistrations = useCallback(async () => {
    const firstResponse = await getMyRegistrations({ page: 1, pageSize: 100, status: 'ACTIVE' });
    const firstPageData = firstResponse?.data;
    if (!Array.isArray(firstPageData?.items)) {
      throw new Error('Dữ liệu đăng ký học phần không hợp lệ.');
    }
    const registrations = [...firstPageData.items];
    const totalPages = firstPageData.pagination?.total_pages ?? 1;
    for (let page = 2; page <= totalPages; page += 1) {
      const response = await getMyRegistrations({ page, pageSize: 100, status: 'ACTIVE' });
      if (!Array.isArray(response?.data?.items)) {
        throw new Error('Dữ liệu đăng ký học phần không hợp lệ.');
      }
      registrations.push(...response.data.items);
    }
    setActiveRegistrations(registrations);
    setRegistrationsError('');
  }, []);

  useEffect(() => {
    loadCourses();
    loadFeatures();
    refreshActiveRegistrations().catch((error) => {
      setRegistrationsError(
        error.response?.data?.message || error.message || 'Không thể tải trạng thái đăng ký của bạn.',
      );
    });
  }, [loadCourses, loadFeatures, refreshActiveRegistrations]);

  useEffect(() => {
    if (!queueEnabled || queueState?.status !== 'WAITING') return undefined;

    let active = true;
    let timerId;

    const pollStatus = async () => {
      setQueuePolling(true);
      let keepPolling = true;
      try {
        const response = await getQueueStatus();
        if (!active) return;
        const nextState = response?.data;
        setQueueState(nextState);
        saveQueueState(nextState);
        setQueueError('');
        keepPolling = nextState?.status === 'WAITING';
      } catch (error) {
        if (active) {
          setQueueError(getApiErrorMessage(error, 'Không thể cập nhật trạng thái hàng đợi.'));
        }
      } finally {
        if (active) {
          setQueuePolling(false);
          if (keepPolling) {
            timerId = window.setTimeout(pollStatus, QUEUE_POLL_INTERVAL_MS);
          }
        }
      }
    };

    timerId = window.setTimeout(pollStatus, QUEUE_POLL_INTERVAL_MS);
    return () => {
      active = false;
      window.clearTimeout(timerId);
    };
  }, [queueEnabled, queueState?.status]);

  const activeClassIds = useMemo(
    () => new Map(activeRegistrations.map((registration) => [registration.course_class_id, registration])),
    [activeRegistrations],
  );

  const selectableCourses = useMemo(
    () =>
      courses.map((course) =>
        activeClassIds.has(course.course_class_id)
          ? {
            ...course,
            registration_status: 'REGISTERED',
            registration_id: activeClassIds.get(course.course_class_id).registration_id,
          }
          : course,
      ),
    [courses, activeClassIds],
  );

  const filteredCourses = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase('vi');
    return selectableCourses.filter((course) => {
      const matchesSearch =
        !normalizedSearch ||
        [course.class_code, course.course_name, course.course_code]
          .some((value) => value?.toLocaleLowerCase('vi').includes(normalizedSearch));
      return matchesSearch;
    });
  }, [selectableCourses, search]);

  const selectedCourses = useMemo(
    () => selectableCourses.filter((course) => selectedIds.has(course.course_class_id)),
    [selectableCourses, selectedIds],
  );
  const scheduleConflicts = useMemo(() => {
    const conflicts = new Map();
    const blockingCourses = selectableCourses.filter(
      (course) => course.registration_status === 'REGISTERED' || selectedIds.has(course.course_class_id),
    );
    for (const course of selectableCourses) {
      if (course.registration_status === 'REGISTERED' || selectedIds.has(course.course_class_id)) continue;
      const conflictingCourse = blockingCourses.find((blockingCourse) =>
        schedulesOverlap(course.schedule, blockingCourse.schedule),
      );
      if (conflictingCourse) {
        conflicts.set(course.course_class_id, conflictingCourse);
      }
    }
    return conflicts;
  }, [selectableCourses, selectedIds]);
  const selectedCredits = selectedCourses.reduce((total, course) => total + (Number(course.credits) || 0), 0);

  useEffect(() => {
    setSelectedIds((current) => {
      const eligibleIds = new Set(
        selectableCourses
          .filter((course) => course.status === 'OPEN' && course.registration_status !== 'REGISTERED')
          .map((course) => course.course_class_id),
      );
      const next = new Set([...current].filter((id) => eligibleIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [selectableCourses]);

  const toggleCourse = useCallback((courseId) => {
    if (scheduleConflicts.has(courseId)) return;
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(courseId)) next.delete(courseId);
      else next.add(courseId);
      return next;
    });
  }, [scheduleConflicts]);

  const fetchCourseDetail = useCallback(async (course) => {
    setDetailSelection(course);
    setDetailCourse(null);
    setDetailError('');
    setDetailLoading(true);
    try {
      const response = await getCourseClass(course.course_class_id);
      const detail = response?.data?.course_class;
      if (!detail) throw new Error('Dữ liệu chi tiết lớp học phần không hợp lệ.');
      setDetailCourse(detail);
    } catch (error) {
      setDetailError(error.response?.data?.message || error.message || 'Không thể tải chi tiết lớp học phần.');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const closeDetails = useCallback(() => {
    setDetailSelection(null);
    setDetailCourse(null);
    setDetailError('');
  }, []);

  const openConfirmation = useCallback(() => {
    if (!selectedCourses.length) return;
    setRegistrationResults([]);
    setConfirmCourses(selectedCourses);
    setRefreshError('');
  }, [selectedCourses]);

  const updateQueueState = useCallback((nextState) => {
    setQueueState(nextState);
    saveQueueState(nextState);
  }, []);

  const handleJoinQueue = useCallback(async () => {
    setQueueLoading(true);
    setQueueError('');
    try {
      const response = await joinQueue();
      const nextState = response?.data;
      if (!nextState || typeof nextState.queue_enabled !== 'boolean') {
        throw new Error('Phản hồi hàng đợi không hợp lệ.');
      }
      updateQueueState(nextState);
      if (nextState.status === 'NONE') {
        const statusResponse = await getQueueStatus();
        updateQueueState(statusResponse?.data);
      }
    } catch (error) {
      setQueueError(getApiErrorMessage(error, 'Không thể tham gia hàng đợi.'));
    } finally {
      setQueueLoading(false);
    }
  }, [updateQueueState]);

  const refreshQueueStatus = useCallback(async () => {
    setQueueLoading(true);
    setQueueError('');
    try {
      const response = await getQueueStatus();
      updateQueueState(response?.data);
    } catch (error) {
      setQueueError(getApiErrorMessage(error, 'Không thể cập nhật trạng thái hàng đợi.'));
    } finally {
      setQueueLoading(false);
    }
  }, [updateQueueState]);

  const requestCancellation = useCallback((course) => {
    const registration = activeRegistrations.find(
      (item) => item.course_class_id === course.course_class_id,
    );
    if (!registration?.registration_id) {
      setRegistrationsError('Không tìm thấy mã đăng ký để hủy. Hãy tải lại danh sách đăng ký.');
      return;
    }
    setCancelFeedback(null);
    setCancelSelection({
      ...course,
      registration_id: registration.registration_id,
    });
  }, [activeRegistrations]);

  const confirmCancellation = useCallback(async () => {
    if (!cancelSelection?.registration_id) return;
    const { registration_id: registrationId } = cancelSelection;
    let attempt = pendingCancelAttempts.current.get(registrationId);
    if (!attempt) {
      attempt = { idempotencyKey: createIdempotencyKey() };
      pendingCancelAttempts.current.set(registrationId, attempt);
    }

    setCancellingIds((current) => new Set(current).add(cancelSelection.course_class_id));
    setCancelFeedback(null);
    try {
      const response = await cancelRegistration(registrationId, attempt.idempotencyKey);
      if (!response?.success) {
        const responseError = new Error(response?.message || 'Hủy đăng ký chưa thành công.');
        responseError.response = { data: response };
        throw responseError;
      }

      pendingCancelAttempts.current.delete(registrationId);
      const courseName = response.data?.registration?.course_name || cancelSelection.course_name;
      setCancelSelection(null);
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(cancelSelection.course_class_id);
        return next;
      });
      setCancelFeedback({
        type: 'success',
        message: `Đã hủy đăng ký lớp ${cancelSelection.class_code} · ${courseName}.`,
      });

      const [coursesUpdated, registrationsUpdated] = await Promise.all([
        loadCourses(),
        refreshActiveRegistrations().then(() => true).catch((error) => {
          setRegistrationsError(
            error.response?.data?.message || error.message || 'Không thể làm mới danh sách đăng ký.',
          );
          return false;
        }),
      ]);
      if (!coursesUpdated || !registrationsUpdated) {
        setRefreshError('Đã hủy đăng ký nhưng không thể cập nhật một phần dữ liệu. Vui lòng tải lại trang.');
      }
    } catch (error) {
      const code = error.response?.data?.code;
      const keepKey =
        !error.response ||
        error.code === 'ECONNABORTED' ||
        error.response?.status >= 500 ||
        code === 'REQUEST_IN_PROGRESS' ||
        code === 'SERVICE_BUSY' ||
        code === 'SERVICE_UNAVAILABLE';
      if (!keepKey) pendingCancelAttempts.current.delete(registrationId);
      setCancelFeedback({
        type: 'error',
        message:
          error.response?.data?.message ||
          error.message ||
          'Không thể hủy đăng ký. Vui lòng thử lại.',
        requestId: error.response?.data?.request_id,
      });
    } finally {
      setCancellingIds((current) => {
        const next = new Set(current);
        next.delete(cancelSelection.course_class_id);
        return next;
      });
    }
  }, [cancelSelection, loadCourses, refreshActiveRegistrations]);

  const setCourseResult = useCallback((result) => {
    setRegistrationResults((current) => {
      const next = current.filter((item) => item.courseId !== result.courseId);
      next.push(result);
      return next;
    });
  }, []);

  const closeRegistrationNotice = useCallback(() => {
    setRegistrationResults([]);
    setCancelFeedback(null);
  }, []);

  const submitCourse = useCallback(async (course) => {
    const user = getCurrentUser();
    const courseId = course.course_class_id;
    const identity = {
      courseId,
      classCode: course.class_code,
      courseName: course.course_name,
    };

    if (!user?.student_id) {
      setCourseResult({
        ...identity,
        type: 'error',
        message: 'Không tìm thấy tài khoản đăng nhập. Vui lòng đăng nhập lại.',
        retryable: false,
      });
      return false;
    }
    if (queueEnabled && (queueState?.status !== 'READY' || !queueState.queue_token)) {
      setCourseResult({
        ...identity,
        type: 'error',
        message: 'Chưa đến lượt đăng ký. Vui lòng tham gia hoặc cập nhật hàng đợi.',
        retryable: false,
      });
      return false;
    }

    const payload = {
      student_id: user.student_id,
      course_class_id: courseId,
    };
    let attempt = pendingAttempts.current.get(courseId);
    if (!attempt) {
      attempt = { payload, idempotencyKey: createIdempotencyKey() };
      pendingAttempts.current.set(courseId, attempt);
    }

    setRegisteringIds((current) => new Set(current).add(courseId));
    setCourseResult({ ...identity, type: 'pending', message: 'Đang gửi yêu cầu...' });
    try {
      const response = await registerCourseClass(
        attempt.payload,
        attempt.idempotencyKey,
        queueEnabled ? queueState.queue_token : undefined,
      );
      if (!response?.success) {
        const responseError = new Error(response?.message || 'Đăng ký học phần chưa thành công.');
        responseError.response = { data: response };
        throw responseError;
      }

      pendingAttempts.current.delete(courseId);
      setCourseResult({
        ...identity,
        type: 'success',
        message: 'Đăng ký học phần thành công.',
      });
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(courseId);
        return next;
      });
      return true;
    } catch (error) {
      const code = error.response?.data?.code;
      if (code === 'QUEUE_TOKEN_INVALID') {
        await refreshQueueStatus();
      }
      const retryable = shouldKeepAttempt(error);
      if (!retryable) pendingAttempts.current.delete(courseId);
      setCourseResult({
        ...identity,
        type: 'error',
        message: getApiErrorMessage(error, 'Không thể đăng ký học phần.'),
        requestId: error.response?.data?.request_id,
        retryable,
      });
      return false;
    } finally {
      setRegisteringIds((current) => {
        const next = new Set(current);
        next.delete(courseId);
        return next;
      });
    }
  }, [queueEnabled, queueState, refreshQueueStatus, setCourseResult]);

  const handleRegisterSelected = useCallback(async () => {
    if (!confirmCourses.length || batchProcessing) return;
    setBatchProcessing(true);
    setRefreshError('');

    let hadSuccess = false;
    try {
      for (const course of confirmCourses) {
        const successful = await submitCourse(course);
        hadSuccess = hadSuccess || successful;
      }
      if (hadSuccess) {
        const [coursesUpdated, registrationsResult] = await Promise.all([
          loadCourses(),
          refreshActiveRegistrations().then(() => true).catch(() => false),
        ]);
        if (!coursesUpdated || !registrationsResult) {
          setRefreshError('Đăng ký đã được gửi nhưng không thể làm mới một phần dữ liệu. Vui lòng tải lại trang.');
        }
      }
    } finally {
      setBatchProcessing(false);
      setConfirmCourses([]);
    }
  }, [confirmCourses, batchProcessing, submitCourse, loadCourses, refreshActiveRegistrations]);

  const retryCourse = useCallback(async (courseId) => {
    const course = selectableCourses.find((item) => item.course_class_id === courseId);
    if (!course || registeringIds.has(courseId)) return;
    await submitCourse(course);
  }, [selectableCourses, registeringIds, submitCourse]);

  const registrationReady =
    queueEnabled !== null && (!queueEnabled || (queueState?.status === 'READY' && Boolean(queueState.queue_token)));
  const canStartRegistration = selectedCourses.length > 0 && registrationReady && !batchProcessing;
  const detailModalCourse = detailCourse
    ? { ...detailCourse, registration_status: detailCourse.registration_status || detailSelection?.registration_status }
    : detailSelection;

  return (
    <DashboardLayout role="STUDENT" pageTitle="Đăng ký học phần">
      <div className="space-y-4 pb-32">
        <div>
          <Link
            to="/student/dashboard"
            className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-red-700"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-red-600 text-white shadow-sm transition hover:bg-red-700">
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            </span>
            Trang chủ sinh viên
          </Link>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-2xl font-bold text-gray-900">Đăng ký lớp học phần</h2>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                to="/student/my-courses"
                className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-white px-4 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-50"
              >
                Học phần đã đăng ký
              </Link>
              <button
                type="button"
                onClick={loadCourses}
                disabled={coursesLoading}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-60"
              >
                <RefreshCw className={`h-4 w-4 ${coursesLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
                Làm mới danh sách
              </button>
            </div>
          </div>
        </div>

        <RegistrationResult
          results={registrationResults}
          cancelFeedback={cancelFeedback}
          registeringIds={registeringIds}
          onRetry={retryCourse}
          onClose={closeRegistrationNotice}
        />

        {registrationsError && (
          <div role="alert" className="flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-amber-800">{registrationsError}</p>
            <button
              type="button"
              onClick={() => refreshActiveRegistrations().catch((error) => {
                setRegistrationsError(
                  error.response?.data?.message || error.message || 'Không thể tải trạng thái đăng ký của bạn.',
                );
              })}
              className="shrink-0 rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm font-semibold text-amber-800 hover:bg-amber-100"
            >
              Tải lại trạng thái
            </button>
          </div>
        )}

        {refreshError && (
          <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            {refreshError}
          </p>
        )}

        {featuresError && (
          <div role="alert" className="flex flex-col gap-3 rounded-lg border border-red-200 bg-red-50 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-red-700">{featuresError}</p>
            <button
              type="button"
              onClick={loadFeatures}
              disabled={featuresLoading}
              className="shrink-0 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60"
            >
              Thử kiểm tra lại
            </button>
          </div>
        )}

        {!featuresError && !featuresLoading && queueEnabled && (
          <QueueStatus
            enabled
            state={queueState}
            loading={queueLoading || queuePolling}
            error={queueError}
            onJoin={handleJoinQueue}
            onRefresh={refreshQueueStatus}
          />
        )}

        <div className="w-full">
          <CourseSearch value={search} onChange={setSearch} />
        </div>

        {!featuresError && featuresLoading && (
          <p className="text-sm text-gray-500" role="status">Đang kiểm tra trạng thái đăng ký...</p>
        )}

        <CourseList
          courses={filteredCourses}
          loading={coursesLoading}
          error={coursesError}
          onRetry={loadCourses}
          onDetails={fetchCourseDetail}
          selectedIds={selectedIds}
          scheduleConflicts={scheduleConflicts}
          onToggle={toggleCourse}
          registeringIds={registeringIds}
          cancellingIds={cancellingIds}
          onCancel={requestCancellation}
          selectionDisabled={batchProcessing}
        />
      </div>

      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-gray-200 bg-white/95 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-700">
              <BookOpen className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="font-semibold text-gray-900">
                {selectedCourses.length} lớp đã chọn
              </p>
              <p className="text-sm text-gray-500">{selectedCredits} tín chỉ</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => openConfirmation()}
            disabled={!canStartRegistration}
            title={!registrationReady ? 'Vui lòng chờ đến lượt đăng ký.' : undefined}
            className="w-full rounded-lg bg-red-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300 sm:w-auto"
          >
            Đăng ký học phần
          </button>
        </div>
      </div>

      {detailSelection && (
        <CourseDetailModal
          course={detailModalCourse}
          loading={detailLoading}
          error={detailError}
          onRetry={() => fetchCourseDetail(detailSelection)}
          onClose={closeDetails}
        />
      )}

      {confirmCourses.length > 0 && (
        <RegistrationConfirmModal
          courses={confirmCourses}
          loading={batchProcessing}
          queueEnabled={queueEnabled === true}
          onClose={() => {
            if (!batchProcessing) setConfirmCourses([]);
          }}
          onConfirm={handleRegisterSelected}
        />
      )}

      {cancelSelection && createPortal(
        <div
          className="fixed inset-0 z-70 flex items-end justify-center bg-gray-950/40 p-0 sm:items-center sm:p-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !cancellingIds.has(cancelSelection.course_class_id)) {
              setCancelSelection(null);
            }
          }}
        >
          <section
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="cancel-registration-title"
            aria-describedby="cancel-registration-description"
            className="w-full rounded-t-2xl bg-white p-6 shadow-xl sm:max-w-md sm:rounded-2xl"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 id="cancel-registration-title" className="text-lg font-bold text-gray-900">
                  Xác nhận hủy đăng ký
                </h2>
                <p id="cancel-registration-description" className="mt-2 text-sm leading-6 text-gray-600">
                  Bạn có chắc chắn muốn hủy lớp <strong>{cancelSelection.class_code}</strong> · {cancelSelection.course_name}?
                  Lớp học sẽ được gỡ khỏi danh sách đã đăng ký.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setCancelSelection(null)}
                disabled={cancellingIds.has(cancelSelection.course_class_id)}
                className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 disabled:opacity-50"
                aria-label="Đóng xác nhận hủy"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setCancelSelection(null)}
                disabled={cancellingIds.has(cancelSelection.course_class_id)}
                className="rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Giữ đăng ký
              </button>
              <button
                type="button"
                onClick={confirmCancellation}
                disabled={cancellingIds.has(cancelSelection.course_class_id)}
                className="rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
              >
                {cancellingIds.has(cancelSelection.course_class_id) ? 'Đang hủy...' : 'Xác nhận hủy'}
              </button>
            </div>
          </section>
        </div>
      , document.body)}
    </DashboardLayout>
  );
}
