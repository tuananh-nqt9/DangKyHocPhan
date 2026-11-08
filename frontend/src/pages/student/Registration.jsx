import { ArrowLeft, BookOpenCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import DashboardLayout from '../../components/common/DashboardLayout.jsx';

export default function StudentRegistration() {
  return (
    <DashboardLayout role="STUDENT" pageTitle="Đăng ký học phần">
      <section className="rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-red-50 text-red-600">
          <BookOpenCheck className="h-7 w-7" aria-hidden="true" />
        </div>
        <h2 className="mt-4 text-xl font-semibold text-gray-900">Đăng ký học phần</h2>
        <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-gray-600">
          Trang đăng ký học phần đang được hoàn thiện. Bạn có thể quay lại trang chủ sinh viên.
        </p>
        <Link
          to="/student/dashboard"
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-600 focus:ring-offset-2"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Về trang chủ sinh viên
        </Link>
      </section>
    </DashboardLayout>
  );
}
