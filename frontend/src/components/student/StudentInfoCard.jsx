import { BadgeCheck, IdCard, UserRound } from 'lucide-react';

export default function StudentInfoCard({ user, sessionActive }) {
  return (
    <section className="h-full min-h-[320px] rounded-2xl border border-gray-200 bg-white p-7 shadow-sm sm:p-8">
      <div className="flex items-start gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600">
          <IdCard className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-gray-900">Thông tin sinh viên</h2>
          <p className="mt-1 text-sm text-gray-500">Thông tin tài khoản của bạn</p>
        </div>
      </div>

      <dl className="mt-8 divide-y divide-gray-100">
        <div className="flex items-center justify-between gap-3 py-4">
          <dt className="flex items-center gap-2 text-sm text-gray-500">
            <IdCard className="h-4 w-4" aria-hidden="true" />
            Mã sinh viên
          </dt>
          <dd className="break-all text-right text-sm font-medium text-gray-900">{user?.student_id || '—'}</dd>
        </div>
        <div className="flex items-center justify-between gap-3 py-4">
          <dt className="flex items-center gap-2 text-sm text-gray-500">
            <UserRound className="h-4 w-4" aria-hidden="true" />
            Họ và tên
          </dt>
          <dd className="max-w-[60%] text-right text-sm font-medium text-gray-900">{user?.full_name || '—'}</dd>
        </div>
        <div className="flex items-center justify-between gap-3 py-4">
          <dt className="text-sm text-gray-500">Vai trò</dt>
          <dd className="text-sm font-medium text-gray-900">Sinh viên</dd>
        </div>
        <div className="flex items-center justify-between gap-3 py-4">
          <dt className="text-sm text-gray-500">Trạng thái phiên</dt>
          <dd>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                sessionActive ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600'
              }`}
            >
              <BadgeCheck className="h-3.5 w-3.5" aria-hidden="true" />
              {sessionActive ? 'Đang hoạt động' : 'Không hoạt động'}
            </span>
          </dd>
        </div>
      </dl>
    </section>
  );
}
