import { ArrowRight, BookOpen, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function RegistrationStatsCard({ count, loading, error, onRetry }) {
  return (
    <section className="flex h-full min-h-80 flex-col rounded-2xl border border-gray-200 bg-white p-7 shadow-sm sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Học phần đã đăng ký</h2>
        </div>
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600">
          <BookOpen className="h-6 w-6" aria-hidden="true" />
        </div>
      </div>

      {loading ? (
        <div className="mt-10" role="status" aria-label="Đang tải số học phần đã đăng ký">
          <div className="h-10 w-20 animate-pulse rounded-lg bg-gray-100" />
          <div className="mt-3 h-4 w-40 animate-pulse rounded bg-gray-100" />
          <span className="sr-only">Đang tải dữ liệu đăng ký...</span>
        </div>
      ) : error ? (
        <div className="mt-8" role="alert">
          <p className="text-sm text-red-700">{error}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-red-700 hover:text-red-800"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Thử tải lại
          </button>
        </div>
      ) : (
        <div className="mt-10">
          <p className="text-5xl font-bold tracking-tight text-gray-900">{count}</p>
          <p className="mt-3 text-sm text-gray-500">
            {count === 0 ? 'Bạn chưa đăng ký học phần nào.' : 'học phần'}
          </p>
        </div>
      )}
      <Link
        to="/student/my-courses"
        className="mt-auto inline-flex w-fit items-center gap-2 rounded-lg border border-red-200 px-4 py-2.5 text-sm font-semibold text-red-700 transition hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
      >
        Học phần của tôi
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </Link>
    </section>
  );
}
