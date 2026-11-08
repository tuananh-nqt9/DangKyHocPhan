import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, X } from 'lucide-react';

export default function RegistrationConfirmModal({ courses, loading, queueEnabled, onClose, onConfirm }) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !loading) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [loading, onClose]);

  if (!courses?.length) return null;

  const totalCredits = courses.reduce((total, course) => total + (Number(course.credits) || 0), 0);

  return createPortal(
    <div
      className="fixed inset-0 z-60 flex items-end justify-center bg-gray-950/40 p-0 sm:items-center sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !loading) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="registration-confirm-title"
        className="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-white p-6 shadow-xl sm:max-w-xl sm:rounded-2xl sm:p-7"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="registration-confirm-title" className="text-lg font-bold text-gray-900">
              Xác nhận đăng ký
            </h2>
            <p className="mt-1 text-sm text-gray-500">Kiểm tra danh sách lớp trước khi gửi yêu cầu.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 disabled:opacity-50"
            aria-label="Đóng xác nhận đăng ký"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="mt-5 divide-y divide-gray-100 rounded-lg border border-gray-200">
          {courses.map((course) => (
            <div key={course.course_class_id} className="flex flex-col gap-1 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-red-700">{course.class_code}</p>
                <p className="mt-1 font-semibold text-gray-900">{course.course_name}</p>
                <p className="mt-1 text-sm text-gray-500">{course.credits} tín chỉ</p>
              </div>
            </div>
          ))}
          <div className="bg-gray-50 px-4 py-3 text-sm font-semibold text-gray-900">
            <span>{courses.length} lớp · {totalCredits} tín chỉ</span>
          </div>
        </div>

        {queueEnabled && (
          <p className="mt-4 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-800">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            Hệ thống đang sử dụng hàng đợi. Các yêu cầu sẽ gửi kèm token lượt đăng ký của bạn.
          </p>
        )}

        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Hủy
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
          >
            {loading ? 'Đang xử lý danh sách...' : `Xác nhận`}
          </button>
        </div>
      </section>
    </div>
    ,
    document.body,
  );
}
