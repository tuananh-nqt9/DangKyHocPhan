import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { AlertTriangle, BookOpen, ChevronLeft, ChevronRight, Eye, Pencil, Plus, RefreshCw, Search, X } from 'lucide-react';
import DashboardLayout from '../../components/common/DashboardLayout.jsx';
import {
  createCourseClass,
  getAdminCourseClass,
  getAllAdminCourseClasses,
  updateCourseClass,
  updateCourseClassStatus,
} from '../../services/adminService';
import type { CourseClass, CourseClassStatus, CourseClassUpsertRequest, ScheduleItem } from '../../services/adminTypes';

const PAGE_SIZE = 10;
const weekDays: ScheduleItem['day_of_week'][] = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
const dayLabels: Record<ScheduleItem['day_of_week'], string> = {
  MON: 'Thứ 2', TUE: 'Thứ 3', WED: 'Thứ 4', THU: 'Thứ 5',
  FRI: 'Thứ 6', SAT: 'Thứ 7', SUN: 'Chủ nhật',
};
const catalogCourses = [
  { course_code: 'CS101', course_name: 'Nhập môn lập trình', credits: 3 },
  { course_code: 'CNNT', course_name: 'Công nghệ nền tảng', credits: 3 },
  { course_code: 'WEB', course_name: 'Phát triển ứng dụng Web', credits: 3 },
  { course_code: 'JAVA', course_name: 'Lập trình hướng đối tượng với Java', credits: 3 },
  { course_code: 'DB101', course_name: 'Cơ sở dữ liệu', credits: 3 },
  { course_code: 'NET101', course_name: 'Mạng máy tính', credits: 3 },
  { course_code: 'SE101', course_name: 'Công nghệ phần mềm', credits: 3 },
  { course_code: 'AI101', course_name: 'Trí tuệ nhân tạo', credits: 3 },
] as const;

interface CourseDraft {
  class_code: string;
  course_code: string;
  course_name: string;
  credits: string;
  capacity: string;
  status: CourseClassStatus;
  schedule: ScheduleItem[];
  prerequisite_course_codes: string;
}

const emptyDraft: CourseDraft = {
  class_code: '',
  course_code: '',
  course_name: '',
  credits: '3',
  capacity: '50',
  status: 'OPEN',
  schedule: [],
  prerequisite_course_codes: '',
};

function getErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = error.response;
    if (typeof response === 'object' && response !== null && 'data' in response) {
      const data = response.data;
      if (typeof data === 'object' && data !== null) {
        const message = 'message' in data && typeof data.message === 'string' ? data.message : '';
        if ('errors' in data && Array.isArray(data.errors)) {
          const details = data.errors
            .map((item) => {
              const field = typeof item?.field === 'string' ? `${item.field}: ` : '';
              return typeof item?.message === 'string' ? `${field}${item.message}` : '';
            })
            .filter(Boolean);
          if (details.length) return [message, ...details].filter(Boolean).join(' ');
        }
        if (message) return message;
      }
    }
  }
  return error instanceof Error ? error.message : 'Đã xảy ra lỗi. Vui lòng thử lại.';
}

function toDraft(course?: CourseClass | null): CourseDraft {
  if (!course) return { ...emptyDraft, schedule: [] };
  return {
    class_code: course.class_code,
    course_code: course.course_code,
    course_name: course.course_name,
    credits: String(course.credits),
    capacity: String(course.capacity),
    status: course.status,
    schedule: course.schedule.map((item) => ({ ...item })),
    prerequisite_course_codes: course.prerequisites.map((item) => item.course_code).join(', '),
  };
}

function suggestClassCode(courseCode: string, courses: CourseClass[]): string {
  const existingCodes = new Set(courses.map((course) => course.class_code.toLocaleUpperCase()));
  const prefix = `${courseCode}-`;
  const nextNumber = courses.reduce((highest, course) => {
    const code = course.class_code.toLocaleUpperCase();
    if (!code.startsWith(prefix.toLocaleUpperCase())) return highest;
    const suffix = code.slice(prefix.length);
    if (!/^\d+$/.test(suffix)) return highest;
    return Math.max(highest, Number(suffix));
  }, 0) + 1;

  let number = nextNumber;
  let candidate = `${prefix}${String(number).padStart(2, '0')}`;
  while (existingCodes.has(candidate.toLocaleUpperCase())) {
    number += 1;
    candidate = `${prefix}${String(number).padStart(2, '0')}`;
  }
  return candidate;
}

function toPayload(draft: CourseDraft): CourseClassUpsertRequest {
  return {
    class_code: draft.class_code.trim(),
    course_code: draft.course_code.trim(),
    course_name: draft.course_name.trim(),
    credits: Number(draft.credits),
    capacity: Number(draft.capacity),
    status: draft.status,
    schedule: draft.schedule.map((item) => ({
      ...item,
      room: item.room.trim(),
    })),
    prerequisite_course_codes: [...new Set(
      draft.prerequisite_course_codes.split(/[\s,;]+/).map((code) => code.trim().toUpperCase()).filter(Boolean),
    )],
  };
}

function ModalFrame({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-gray-950/40 p-0 sm:items-center sm:p-4" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section role="dialog" aria-modal="true" aria-label={title} className="max-h-[92vh] w-full overflow-y-auto bg-white p-5 shadow-xl sm:max-w-3xl sm:p-7">
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 className="text-xl font-bold text-gray-900">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Đóng" className="p-2 text-gray-500 hover:bg-gray-100"><X className="h-5 w-5" /></button>
        </div>
        {children}
      </section>
    </div>
  );
}

export default function CourseClasses() {
  const [courses, setCourses] = useState<CourseClass[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | CourseClassStatus>('ALL');
  const [sortBy, setSortBy] = useState<'class_code' | 'course_name' | 'registered_count'>('class_code');
  const [page, setPage] = useState(1);
  const [formCourse, setFormCourse] = useState<CourseClass | null | undefined>(undefined);
  const [draft, setDraft] = useState<CourseDraft>(toDraft());
  const [selectedCatalogCode, setSelectedCatalogCode] = useState('');
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState<CourseClass | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<CourseClass | null>(null);
  const [updatingStatus, setUpdatingStatus] = useState(false);

  const loadCourses = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      setCourses(await getAllAdminCourseClasses());
    } catch (error) {
      setLoadError(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadCourses();
  }, [loadCourses]);

  const visibleCourses = useMemo(() => {
    const search = query.trim().toLocaleLowerCase('vi');
    return courses
      .filter((course) => statusFilter === 'ALL' || course.status === statusFilter)
      .filter((course) => !search || [course.class_code, course.course_code, course.course_name]
        .some((value) => value.toLocaleLowerCase('vi').includes(search)))
      .sort((a, b) => sortBy === 'registered_count'
        ? b.registered_count - a.registered_count
        : a[sortBy].localeCompare(b[sortBy], 'vi'));
  }, [courses, query, sortBy, statusFilter]);
  const pageCount = Math.max(1, Math.ceil(visibleCourses.length / PAGE_SIZE));
  const pageCourses = visibleCourses.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setPage(1), [query, statusFilter, sortBy]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  useEffect(() => {
    if (!notice) return undefined;
    const timeoutId = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timeoutId);
  }, [notice]);

  const startCreate = () => {
    const template = catalogCourses[0];
    const existingClass = courses.find((course) => course.course_code === template.course_code);
    setSelectedCatalogCode(template.course_code);
    setDraft({
      ...toDraft(),
      class_code: suggestClassCode(template.course_code, courses),
      course_code: template.course_code,
      course_name: template.course_name,
      credits: String(template.credits),
      prerequisite_course_codes: existingClass?.prerequisites.map((item) => item.course_code).join(', ') ?? '',
    });
    setFormCourse(null);
  };

  const startEdit = (course: CourseClass) => {
    setSelectedCatalogCode(course.course_code);
    setDraft(toDraft(course));
    setFormCourse(course);
  };

  const selectCatalogCourse = (courseCode: string) => {
    const template = catalogCourses.find((course) => course.course_code === courseCode);
    if (!template) return;
    const existingClass = courses.find((course) => course.course_code === courseCode);
    setSelectedCatalogCode(courseCode);
    setDraft((current) => ({
      ...current,
      class_code: suggestClassCode(courseCode, courses),
      course_code: template.course_code,
      course_name: template.course_name,
      credits: String(template.credits),
      prerequisite_course_codes: existingClass?.prerequisites.map((item) => item.course_code).join(', ') ?? '',
    }));
  };

  const openDetails = async (course: CourseClass) => {
    setDetailLoading(true);
    setDetail(null);
    try {
      setDetail(await getAdminCourseClass(course.course_class_id));
    } catch (error) {
      setNotice({ type: 'error', text: getErrorMessage(error) });
    } finally {
      setDetailLoading(false);
    }
  };

  const saveCourse = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice(null);
    setSaving(true);
    try {
      const payload = toPayload(draft);
      if (formCourse) {
        await updateCourseClass(formCourse.course_class_id, payload);
        setNotice({ type: 'success', text: 'Đã cập nhật lớp học phần.' });
      } else {
        await createCourseClass(payload);
        setNotice({ type: 'success', text: 'Đã tạo lớp học phần.' });
      }
      setFormCourse(undefined);
      await loadCourses();
    } catch (error) {
      setNotice({ type: 'error', text: getErrorMessage(error) });
    } finally {
      setSaving(false);
    }
  };

  const changeStatus = async () => {
    if (!pendingStatus) return;
    setUpdatingStatus(true);
    setNotice(null);
    const nextStatus: CourseClassStatus = pendingStatus.status === 'OPEN' ? 'CLOSED' : 'OPEN';
    try {
      await updateCourseClassStatus(pendingStatus.course_class_id, nextStatus);
      setNotice({ type: 'success', text: `Đã ${nextStatus === 'OPEN' ? 'mở' : 'đóng'} lớp ${pendingStatus.class_code}.` });
      setPendingStatus(null);
      await loadCourses();
    } catch (error) {
      setNotice({ type: 'error', text: getErrorMessage(error) });
    } finally {
      setUpdatingStatus(false);
    }
  };

  const updateSchedule = (index: number, patch: Partial<ScheduleItem>) => {
    setDraft((current) => ({
      ...current,
      schedule: current.schedule.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    }));
  };

  return (
    <DashboardLayout role="ADMIN" pageTitle="Quản lý lớp học phần" stickyHeader>
      <div className="space-y-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-red-700">Danh mục đào tạo</p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={loadCourses} disabled={loading} className="inline-flex items-center gap-2 border border-gray-200 bg-white px-3 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-60">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Làm mới
            </button>
            <button type="button" onClick={startCreate} disabled={loading} className="inline-flex items-center gap-2 bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50">
              <Plus className="h-4 w-4" /> Thêm lớp
            </button>
          </div>
        </div>

        {loadError && <div role="alert" className="border border-red-200 bg-red-50 p-4 text-sm text-red-700">{loadError}</div>}

        <section className="border border-gray-200 bg-white p-4 shadow-sm">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_220px]">
            <label className="relative block">
              <span className="sr-only">Tìm lớp học phần</span>
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm mã lớp, mã học phần, tên học phần..." className="w-full border border-gray-200 py-2.5 pl-9 pr-3 text-sm outline-none focus:border-red-400 focus:ring-2 focus:ring-red-100" />
            </label>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as 'ALL' | CourseClassStatus)} aria-label="Lọc trạng thái" className="border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-700 outline-none focus:border-red-400">
              <option value="ALL">Tất cả trạng thái</option>
              <option value="OPEN">Đang mở</option>
              <option value="CLOSED">Đã đóng</option>
            </select>
            <select value={sortBy} onChange={(event) => setSortBy(event.target.value as typeof sortBy)} aria-label="Sắp xếp" className="border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-700 outline-none focus:border-red-400">
              <option value="class_code">Sắp xếp: Mã lớp</option>
              <option value="course_name">Sắp xếp: Tên học phần</option>
              <option value="registered_count">Sắp xếp: Lượt đăng ký</option>
            </select>
          </div>
        </section>

        <section className="overflow-hidden border border-gray-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-212.5 text-left text-sm">
              <thead className="bg-gray-50 text-xs font-semibold uppercase tracking-wide text-gray-600">
                <tr>
                  <th className="px-4 py-3">Mã lớp / Học phần</th>
                  <th className="px-4 py-3">Tên học phần</th>
                  <th className="px-4 py-3">Tín chỉ</th>
                  <th className="px-4 py-3">Đăng ký / Sức chứa</th>
                  <th className="px-4 py-3">Trạng thái</th>
                  <th className="px-4 py-3 pr-7 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {loading ? (
                  <tr><td colSpan={6} className="px-4 py-12 text-center text-gray-500">Đang tải danh sách lớp...</td></tr>
                ) : pageCourses.length ? pageCourses.map((course) => (
                  <tr key={course.course_class_id} className="hover:bg-gray-50">
                    <td className="px-4 py-4">
                      <p className="font-semibold text-red-700">{course.class_code}</p>
                      <p className="mt-1 text-xs text-gray-500">{course.course_code}</p>
                    </td>
                    <td className="px-4 py-4 font-medium text-gray-900">{course.course_name}</td>
                    <td className="px-4 py-4 text-gray-600">{course.credits}</td>
                    <td className="px-4 py-4 text-gray-600">{course.registered_count} / {course.capacity}</td>
                    <td className="px-4 py-4">
                      <span className={`px-2.5 py-1 text-xs font-medium ${
                        course.status === 'OPEN' ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600'
                      }`}>{course.status === 'OPEN' ? 'Đang mở' : 'Đã đóng'}</span>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex justify-end gap-1 pr-3">
                        <button type="button" onClick={() => openDetails(course)} aria-label={`Xem ${course.class_code}`} className="p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900"><Eye className="h-4 w-4" /></button>
                        <button type="button" onClick={() => startEdit(course)} aria-label={`Sửa ${course.class_code}`} className="p-2 text-gray-500 hover:bg-red-50 hover:text-red-700"><Pencil className="h-4 w-4" /></button>
                        <button type="button" onClick={() => setPendingStatus(course)} className={`px-2 py-1 text-xs font-semibold ${
                          course.status === 'OPEN' ? 'text-red-700 hover:bg-amber-50' : 'text-green-700 hover:bg-green-50'
                        }`}>{course.status === 'OPEN' ? 'Đóng' : 'Mở'}</button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr><td colSpan={6} className="px-4 py-12 text-center">
                    <BookOpen className="mx-auto h-9 w-9 text-gray-300" />
                    <p className="mt-3 font-medium text-gray-800">Không tìm thấy lớp học phần</p>
                    <p className="mt-1 text-sm text-gray-500">Thử thay đổi từ khóa hoặc bộ lọc.</p>
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 px-4 py-3">
            <p className="text-xs text-gray-500">{visibleCourses.length} lớp học phần</p>
            <nav aria-label="Phân trang lớp học phần" className="flex items-center gap-1">
              <button type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page <= 1} aria-label="Trang trước" className="p-2 text-gray-600 hover:bg-gray-100 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button>
              <span className="px-2 text-xs text-gray-600">Trang {page} / {pageCount}</span>
              <button type="button" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={page >= pageCount} aria-label="Trang sau" className="p-2 text-gray-600 hover:bg-gray-100 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button>
            </nav>
          </div>
        </section>
      </div>

      {notice && (
        <div
          role={notice.type === 'error' ? 'alert' : 'status'}
          aria-live={notice.type === 'error' ? 'assertive' : 'polite'}
          className={`fixed right-4 top-4 z-60 flex w-[min(24rem,calc(100vw-2rem))] items-start justify-between gap-4 border px-4 py-3 text-sm shadow-lg ${
            notice.type === 'success'
              ? 'border-green-300 bg-white text-green-800'
              : 'border-red-300 bg-white text-red-700'
          }`}
        >
          <span>{notice.text}</span>
          <button type="button" onClick={() => setNotice(null)} aria-label="Đóng thông báo" className="shrink-0 p-0.5">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {formCourse !== undefined && (
        <ModalFrame title={formCourse ? `Chỉnh sửa lớp ${formCourse.class_code}` : 'Thêm lớp học phần'} onClose={() => setFormCourse(undefined)}>
          <form onSubmit={saveCourse} className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              {formCourse === null && (
                <label className="block text-sm font-medium text-gray-700 sm:col-span-2">
                  Chọn học phần
                  <select
                    required
                    value={selectedCatalogCode}
                    onChange={(event) => selectCatalogCourse(event.target.value)}
                    className="mt-1.5 w-full border border-gray-200 bg-white px-3 py-2.5 font-normal outline-none focus:border-red-400"
                  >
                    {catalogCourses.map((course) => (
                      <option key={course.course_code} value={course.course_code}>
                        {course.course_code} · {course.course_name}
                      </option>
                    ))}
                  </select>
                 
                </label>
              )}
              <label className="block text-sm font-medium text-gray-700">
                Mã lớp {formCourse === null && <span className="font-normal text-gray-500"></span>}
                <input
                  required
                  maxLength={100}
                  value={draft.class_code}
                  onChange={(event) => setDraft((current) => ({ ...current, class_code: event.target.value }))}
                  placeholder="Mã lớp"
                  className="mt-1.5 w-full border border-gray-200 px-3 py-2.5 font-normal outline-none focus:border-red-400 focus:ring-2 focus:ring-red-100"
                />
              </label>
              <label className="block text-sm font-medium text-gray-700">
                Mã học phần
                <input
                  required
                  maxLength={100}
                  readOnly={formCourse === null}
                  value={draft.course_code}
                  onChange={(event) => setDraft((current) => ({ ...current, course_code: event.target.value }))}
                  placeholder="Mã học phần"
                  className="mt-1.5 w-full border border-gray-200 px-3 py-2.5 font-normal outline-none read-only:bg-gray-50 focus:border-red-400 focus:ring-2 focus:ring-red-100"
                />
              </label>
              <label className="block text-sm font-medium text-gray-700 sm:col-span-2">
                Tên học phần
                <input
                  required
                  maxLength={100}
                  readOnly={formCourse === null}
                  value={draft.course_name}
                  onChange={(event) => setDraft((current) => ({ ...current, course_name: event.target.value }))}
                  placeholder="Tên học phần"
                  className="mt-1.5 w-full border border-gray-200 px-3 py-2.5 font-normal outline-none read-only:bg-gray-50 focus:border-red-400 focus:ring-2 focus:ring-red-100"
                />
              </label>
            
              <label className="block text-sm font-medium text-gray-700">Số tín chỉ
                <input required type="number" min={1} max={30} readOnly={formCourse === null} value={draft.credits} onChange={(event) => setDraft((current) => ({ ...current, credits: event.target.value }))} className="mt-1.5 w-full border border-gray-200 px-3 py-2.5 font-normal outline-none read-only:bg-gray-50 focus:border-red-400" />
              </label>
              <label className="block text-sm font-medium text-gray-700">Sức chứa
                <input required type="number" min={1} max={10000} value={draft.capacity} onChange={(event) => setDraft((current) => ({ ...current, capacity: event.target.value }))} className="mt-1.5 w-full border border-gray-200 px-3 py-2.5 font-normal outline-none focus:border-red-400" />
              </label>
              <label className="block text-sm font-medium text-gray-700">Trạng thái ban đầu
                <select value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value as CourseClassStatus }))} className="mt-1.5 w-full border border-gray-200 bg-white px-3 py-2.5 font-normal">
                  <option value="OPEN">Đang mở</option><option value="CLOSED">Đã đóng</option>
                </select>
              </label>
            </div>

            <div>
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-gray-900">Lịch học</h3>
                <button type="button" onClick={() => setDraft((current) => ({ ...current, schedule: [...current.schedule, { day_of_week: 'MON', start_period: 1, end_period: 1, room: '' }] }))} className="text-sm font-semibold text-red-700 hover:text-red-800">+ Thêm lịch</button>
              </div>
              {draft.schedule.length ? <div className="mt-2 space-y-2">
                {draft.schedule.map((item, index) => (
                  <div key={index} className="grid gap-2 border border-gray-100 p-3 sm:grid-cols-[1.2fr_1fr_1fr_1.2fr_auto]">
                    <select value={item.day_of_week} onChange={(event) => updateSchedule(index, { day_of_week: event.target.value as ScheduleItem['day_of_week'] })} aria-label="Thứ" className="border border-gray-200 px-2 py-2 text-sm">{weekDays.map((day) => <option key={day} value={day}>{dayLabels[day]}</option>)}</select>
                    <label className="text-xs text-gray-500">Tiết bắt đầu<input type="number" min={1} max={12} required value={item.start_period} onChange={(event) => updateSchedule(index, { start_period: Number(event.target.value) })} className="mt-1 w-full border border-gray-200 px-2 py-2 text-sm text-gray-900" /></label>
                    <label className="text-xs text-gray-500">Tiết kết thúc<input type="number" min={1} max={12} required value={item.end_period} onChange={(event) => updateSchedule(index, { end_period: Number(event.target.value) })} className="mt-1 w-full border border-gray-200 px-2 py-2 text-sm text-gray-900" /></label>
                    <label className="text-xs text-gray-500">Phòng<input required value={item.room} onChange={(event) => updateSchedule(index, { room: event.target.value })} className="mt-1 w-full border border-gray-200 px-2 py-2 text-sm text-gray-900" /></label>
                    <button type="button" onClick={() => setDraft((current) => ({ ...current, schedule: current.schedule.filter((_, itemIndex) => itemIndex !== index) }))} aria-label="Xóa lịch học" className="self-center p-2 text-gray-500 hover:bg-red-50 hover:text-red-700"><X className="h-4 w-4" /></button>
                  </div>
                ))}
              </div> : <p></p>}
            </div>
            <label className="block text-sm font-medium text-gray-700">Mã học phần tiên quyết
              <input readOnly={formCourse === null} value={draft.prerequisite_course_codes} onChange={(event) => setDraft((current) => ({ ...current, prerequisite_course_codes: event.target.value }))} placeholder="Không yêu cầu" className="mt-1.5 w-full border border-gray-200 px-3 py-2.5 font-normal outline-none read-only:bg-gray-50 focus:border-red-400" />
              <span className="mt-1 block text-xs font-normal text-gray-500">
                
              </span>
            </label>
            <div className="flex justify-end gap-2 border-t border-gray-100 pt-4">
              <button type="button" onClick={() => setFormCourse(undefined)} className="border border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50">Hủy</button>
              <button type="submit" disabled={saving} className="bg-red-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60">{saving ? 'Đang lưu...' : formCourse ? 'Lưu thay đổi' : 'Tạo lớp'}</button>
            </div>
          </form>
        </ModalFrame>
      )}

      {(detail || detailLoading) && (
        <ModalFrame title="Chi tiết lớp học phần" onClose={() => setDetail(null)}>
          {detailLoading ? <p className="py-8 text-center text-sm text-gray-500">Đang tải chi tiết...</p> : detail && (
            <div className="space-y-4">
              <div>
                <p className="text-sm font-semibold text-red-700">{detail.class_code} · {detail.course_code}</p>
                <h3 className="mt-1 text-xl font-bold text-gray-900">{detail.course_name}</h3>
              </div>
              <div>
                <h4 className="text-sm font-semibold text-gray-900">Lịch học</h4>
                {detail.schedule.length ? detail.schedule.map((item, index) => (
                  <p key={index} className="mt-2 border border-gray-100 px-3 py-2 text-sm text-gray-700">
                    {dayLabels[item.day_of_week]}, tiết {item.start_period}–{item.end_period}, phòng {item.room}
                  </p>
                )) : <p className="mt-2 text-sm text-gray-500">Chưa có lịch học.</p>}
              </div>
              <div>
                <h4 className="text-sm font-semibold text-gray-900">Học phần tiên quyết</h4>
                <p className="mt-2 text-sm text-gray-600">
                  {detail.prerequisites.length ? detail.prerequisites.map((item) => `${item.course_code} · ${item.course_name}`).join(', ') : 'Không yêu cầu.'}
                </p>
              </div>
            </div>
          )}
        </ModalFrame>
      )}

      {pendingStatus && (
        <ModalFrame title="Xác nhận thay đổi trạng thái" onClose={() => setPendingStatus(null)}>
          <div className="flex gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
            <p className="text-sm leading-6 text-gray-700">
              Bạn có chắc muốn {pendingStatus.status === 'OPEN' ? 'đóng' : 'mở'} lớp
              {' '}<strong>{pendingStatus.class_code}</strong> · {pendingStatus.course_name}?
            </p>
          </div>
          <div className="mt-6 flex justify-end gap-2">
            <button type="button" onClick={() => setPendingStatus(null)} className="border border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-700">Hủy</button>
            <button type="button" onClick={changeStatus} disabled={updatingStatus} className="bg-red-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60">
              {updatingStatus ? 'Đang cập nhật...' : 'Xác nhận'}
            </button>
          </div>
        </ModalFrame>
      )}
    </DashboardLayout>
  );
}
