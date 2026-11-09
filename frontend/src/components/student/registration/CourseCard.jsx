import { AlertTriangle, BookOpen, CalendarDays, Check, Circle, LoaderCircle, Users } from 'lucide-react';

const weekDays = {
  MON: 'Thứ 2',
  TUE: 'Thứ 3',
  WED: 'Thứ 4',
  THU: 'Thứ 5',
  FRI: 'Thứ 6',
  SAT: 'Thứ 7',
  SUN: 'Chủ nhật',
};

function getScheduleText(schedule) {
  if (!schedule?.length) return 'Chưa cập nhật lịch học';
  return schedule
    .map((item) => `${weekDays[item.day_of_week] || item.day_of_week}, tiết ${item.start_period}–${item.end_period}`)
    .join(' · ');
}

export default function CourseCard({
  course,
  selected,
  conflictWith,
  selectionDisabled,
  registering,
  cancelling,
  canCancel,
  onToggle,
  onDetails,
  onCancel,
}) {
  const isOpen = course.status === 'OPEN';
  const isFull = course.remaining_seats === 0;
  const alreadyRegistered = course.registration_status === 'REGISTERED';
  const unmetPrerequisites = (course.prerequisites || []).filter((item) => item.satisfied === false);
  const canSelect = isOpen && !alreadyRegistered;
  const selectionBlocked = !canSelect || selectionDisabled ||
    (!selected && (unmetPrerequisites.length > 0 || Boolean(conflictWith)));

  return (
    <article
      className={`grid gap-4 rounded-lg border p-4 transition-colors sm:p-5 md:grid-cols-[auto_minmax(0,1.3fr)_minmax(0,1.7fr)_auto] md:items-center ${
        selected
          ? 'border-red-500 bg-red-50'
          : 'border-gray-200 bg-white hover:border-gray-300'
      } ${!selectionBlocked || selected ? 'cursor-pointer' : ''}`}
      onClick={() => {
        if (
          !selectionDisabled &&
          (selected || (canSelect && unmetPrerequisites.length === 0 && !conflictWith))
        ) {
          onToggle(course.course_class_id);
        }
      }}
    >
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          if (canSelect && !selectionDisabled && (selected || unmetPrerequisites.length === 0)) {
            onToggle(course.course_class_id);
          }
        }}
        disabled={selectionBlocked}
        aria-pressed={selected}
        aria-label={`${selected ? 'Bỏ chọn' : 'Chọn'} lớp ${course.class_code}`}
        className={`flex h-8 w-8 items-center justify-center rounded-full transition focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 ${
          selected
            ? 'bg-red-600 text-white'
            : !selectionBlocked
              ? 'border border-gray-300 bg-white text-transparent hover:border-red-400'
              : 'cursor-not-allowed bg-gray-100 text-gray-300'
        }`}
      >
        {selected ? <Check className="h-4 w-4" aria-hidden="true" /> : <Circle className="h-4 w-4" aria-hidden="true" />}
      </button>

      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-red-700">{course.class_code}</p>
        <h2 className="mt-1 font-semibold leading-6 text-gray-900">{course.course_name}</h2>
        {conflictWith && !selected && (
          <p className="mt-1 flex items-start gap-1.5 text-xs font-medium text-yellow-400">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>Trùng lịch</span>
          </p>
        )}
        {unmetPrerequisites.length > 0 && (
          <p className="mt-1 flex items-start gap-1.5 text-xs font-medium text-yellow-400">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>
              Chưa hoàn thành học phần tiên quyết
              {unmetPrerequisites.some((item) => item.course_name || item.course_code) &&
                `: ${unmetPrerequisites.map((item) => item.course_name || item.course_code).filter(Boolean).join(', ')}`}
            </span>
          </p>
        )}
        {alreadyRegistered && (
          <p className="mt-1 text-xs font-medium text-green-700">Bạn đã đăng ký lớp này</p>
        )}
      </div>

      <div className="grid gap-2 text-sm text-gray-600 sm:grid-cols-2 md:grid-cols-1 xl:grid-cols-2">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />
          <span>{course.credits} tín chỉ</span>
        </div>
        <div className={`flex items-center gap-2 ${isFull ? 'text-red-700' : ''}`}>
          <Users className="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />
          <span>Còn {course.remaining_seats}/{course.capacity} chỗ</span>
        </div>
        <div className="flex items-start gap-2 sm:col-span-2 md:col-span-1 xl:col-span-2">
          <CalendarDays className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />
          <span>{getScheduleText(course.schedule)}</span>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 md:flex-col md:items-end">
        <span
          className={`rounded-md px-2.5 py-1 text-xs font-medium ${
            isOpen ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600'
          }`}
        >
          {isOpen ? 'Đang mở' : 'Đã đóng'}
        </span>
        <div className="flex items-center gap-2">
          {canCancel && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onCancel(course);
              }}
              disabled={registering || cancelling}
              className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 transition hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {cancelling && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />}
              Hủy
            </button>
          )}
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onDetails(course);
            }}
            disabled={registering || cancelling}
            className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-semibold text-gray-700 transition hover:border-red-300 hover:bg-red-50 hover:text-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Chi tiết
          </button>
        </div>
      </div>
    </article>
  );
}
