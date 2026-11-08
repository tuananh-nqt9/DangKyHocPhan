import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { BookOpen, CalendarDays, Clock3, DoorOpen, Users, X } from 'lucide-react';

const weekDays = {
  MON: 'Thứ 2',
  TUE: 'Thứ 3',
  WED: 'Thứ 4',
  THU: 'Thứ 5',
  FRI: 'Thứ 6',
  SAT: 'Thứ 7',
  SUN: 'Chủ nhật',
};

export default function CourseDetailModal({ course, loading, error, onRetry, onClose }) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-gray-950/40 p-0 sm:items-center sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="course-detail-title"
        className="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-white p-6 shadow-xl sm:max-w-2xl sm:rounded-2xl sm:p-8"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-red-700">{course?.class_code || 'Chi tiết lớp học phần'}</p>
            <h2 id="course-detail-title" className="mt-1 text-xl font-bold text-gray-900">
              {course?.course_name || (loading ? 'Đang tải chi tiết...' : 'Chi tiết lớp học phần')}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            aria-label="Đóng chi tiết lớp học phần"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {loading ? (
          <div className="mt-8 space-y-4" role="status" aria-label="Đang tải chi tiết lớp học phần">
            <div className="h-5 w-1/2 animate-pulse rounded bg-gray-100" />
            <div className="h-24 animate-pulse rounded-xl bg-gray-100" />
            <span className="sr-only">Đang tải...</span>
          </div>
        ) : error ? (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4" role="alert">
            <p className="text-sm text-red-700">{error}</p>
            <button type="button" onClick={onRetry} className="mt-3 text-sm font-semibold text-red-700 hover:text-red-800">
              Thử tải lại
            </button>
          </div>
        ) : course ? (
          <>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <div className="flex items-center gap-3 rounded-xl bg-gray-50 p-4">
                <BookOpen className="h-5 w-5 text-red-600" aria-hidden="true" />
                <div>
                  <p className="text-xs text-gray-500">Mã học phần · Tín chỉ</p>
                  <p className="mt-1 text-sm font-medium text-gray-900">{course.course_code} · {course.credits}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-xl bg-gray-50 p-4">
                <Users className="h-5 w-5 text-red-600" aria-hidden="true" />
                <div>
                  <p className="text-xs text-gray-500">Chỗ còn lại</p>
                  <p className="mt-1 text-sm font-medium text-gray-900">{course.remaining_seats}/{course.capacity}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-xl bg-gray-50 p-4">
                <span className={`h-2.5 w-2.5 rounded-full ${course.status === 'OPEN' ? 'bg-green-500' : 'bg-gray-400'}`} />
                <div>
                  <p className="text-xs text-gray-500">Trạng thái lớp</p>
                  <p className="mt-1 text-sm font-medium text-gray-900">{course.status === 'OPEN' ? 'Đang mở' : 'Đã đóng'}</p>
                </div>
              </div>
              {course.registration_status && (
                <div className="flex items-center gap-3 rounded-xl bg-gray-50 p-4">
                  <div>
                    <p className="text-xs text-gray-500">Trạng thái đăng ký của bạn</p>
                    <p className="mt-1 text-sm font-medium text-gray-900">
                      {course.registration_status === 'REGISTERED' ? 'Đã đăng ký' : 'Chưa đăng ký'}
                    </p>
                  </div>
                </div>
              )}
            </div>

            <div className="mt-6">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
                <CalendarDays className="h-4 w-4 text-red-600" aria-hidden="true" />
                Lịch học
              </h3>
              {course.schedule?.length ? (
                <ul className="mt-3 space-y-2">
                  {course.schedule.map((item, index) => (
                    <li key={`${item.day_of_week}-${item.start_period}-${index}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-gray-100 px-4 py-3 text-sm text-gray-700">
                      <span className="min-w-20 font-medium">{weekDays[item.day_of_week] || item.day_of_week}</span>
                      <span className="inline-flex items-center gap-1.5">
                        <Clock3 className="h-4 w-4 text-gray-400" aria-hidden="true" />
                        Tiết {item.start_period}–{item.end_period}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <DoorOpen className="h-4 w-4 text-gray-400" aria-hidden="true" />
                        {item.room}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-gray-500">Chưa cập nhật lịch học.</p>
              )}
            </div>

            <div className="mt-6">
              <h3 className="text-sm font-semibold text-gray-900">Học phần tiên quyết</h3>
              {course.prerequisites?.length ? (
                <ul className="mt-3 space-y-2">
                  {course.prerequisites.map((item) => (
                    <li key={item.course_code} className="flex items-center justify-between gap-3 rounded-xl border border-gray-100 px-4 py-3 text-sm">
                      <span className="text-gray-700">{item.course_code} · {item.course_name}</span>
                      {typeof item.satisfied === 'boolean' && (
                        <span className={item.satisfied ? 'font-medium text-green-700' : 'font-medium text-amber-700'}>
                          {item.satisfied ? 'Đã hoàn thành' : 'Chưa hoàn thành'}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-gray-500">Không yêu cầu học phần tiên quyết.</p>
              )}
            </div>
          </>
        ) : null}

        <div className="mt-8 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
          >
            Đóng
          </button>
        </div>
      </section>
    </div>
    ,
    document.body,
  );
}
