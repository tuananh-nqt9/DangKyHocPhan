import { ArrowRight, BookOpenCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function RegistrationShortcut() {
  return (
    <section className="flex flex-col gap-6 rounded-2xl border border-red-100 bg-white p-7 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:p-8">
      <div className="flex items-start gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600">
          <BookOpenCheck className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Đăng ký học phần</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600">
            Khám phá các lớp học phần và đăng ký môn học cho kỳ học của bạn.
          </p>
        </div>
      </div>
      <Link
        to="/student/registration"
        className="inline-flex w-full shrink-0 items-center justify-center gap-2 rounded-xl bg-red-600 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-600 focus:ring-offset-2 sm:w-auto"
      >
        Đăng ký ngay
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </Link>
    </section>
  );
}
