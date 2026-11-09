import { useEffect, useState } from 'react';
import { BookOpen, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import CourseCard from './CourseCard.jsx';

const PAGE_SIZE = 6;

export default function CourseList({
  courses,
  loading,
  error,
  onRetry,
  onDetails,
  selectedIds,
  scheduleConflicts,
  duplicateCourseConflicts,
  onToggle,
  registeringIds,
  cancellingIds,
  onCancel,
  selectionDisabled,
}) {
  const [page, setPage] = useState(1);
  const pageCount = Math.ceil(courses.length / PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [courses]);

  useEffect(() => {
    if (pageCount > 0 && page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  const visibleCourses = courses.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  if (loading) {
    return (
      <div className="space-y-3" role="status" aria-label="Đang tải lớp học phần">
        {[1, 2, 3].map((item) => (
          <div key={item} className="h-28 animate-pulse rounded-lg border border-gray-100 bg-white" />
        ))}
        <span className="sr-only">Đang tải danh sách lớp học phần...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-white p-8 text-center">
        <p className="font-medium text-gray-900">Không thể tải lớp học phần</p>
        <p className="mt-2 text-sm text-red-700">{error}</p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Thử tải lại
        </button>
      </div>
    );
  }

  if (!courses.length) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-white px-6 py-14 text-center">
        <BookOpen className="mx-auto h-10 w-10 text-gray-300" aria-hidden="true" />
        <p className="mt-4 font-medium text-gray-900">Không tìm thấy lớp học phần</p>
        <p className="mt-1 text-sm text-gray-500">Thử đổi từ khóa tìm kiếm hoặc bộ lọc trạng thái.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="space-y-3" aria-live="polite">
        {visibleCourses.map((course) => (
          <CourseCard
            key={course.course_class_id}
            course={course}
            selected={selectedIds.has(course.course_class_id)}
            conflictWith={scheduleConflicts.get(course.course_class_id)}
            duplicateCourseWith={duplicateCourseConflicts.get(course.course_class_id)}
            selectionDisabled={selectionDisabled}
            registering={registeringIds.has(course.course_class_id)}
            cancelling={cancellingIds.has(course.course_class_id)}
            canCancel={Boolean(course.registration_id)}
            onToggle={onToggle}
            onDetails={onDetails}
            onCancel={onCancel}
          />
        ))}
      </div>
      {pageCount > 0 && (
        <nav
          aria-label="Phân trang lớp học phần"
          className="flex shrink-0 items-center justify-end gap-0.5 border-t border-gray-200 bg-gray-50 px-3 py-1.5"
        >
          <button
            type="button"
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            disabled={page === 1}
            aria-label="Trang trước"
            className="flex h-7 w-7 items-center justify-center rounded text-gray-600 hover:bg-white hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          {Array.from({ length: pageCount }, (_, index) => index + 1).map((pageNumber) => (
            <button
              key={pageNumber}
              type="button"
              onClick={() => setPage(pageNumber)}
              aria-label={`Trang ${pageNumber}`}
              aria-current={page === pageNumber ? 'page' : undefined}
              className={`h-7 min-w-7 rounded px-1.5 text-xs font-medium ${
                page === pageNumber
                  ? 'bg-red-600 text-white'
                  : 'text-gray-600 hover:bg-white hover:text-red-700'
              }`}
            >
              {pageNumber}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
            disabled={page === pageCount}
            aria-label="Trang sau"
            className="flex h-7 w-7 items-center justify-center rounded text-gray-600 hover:bg-white hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
          <span className="ml-2 hidden text-xs text-gray-500 sm:inline">
            {courses.length} lớp học phần
          </span>
        </nav>
      )}
    </div>
  );
}
