import { useCallback, useEffect, useState } from 'react';
import {
  ArrowLeft,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../../components/common/DashboardLayout.jsx';
import { getCourseClass } from '../../services/courseService.js';
import { getMyRegistrations } from '../../services/registrationService.js';

const PAGE_SIZE = 20;

const weekDays = {
  MON: 'Thứ 2',
  TUE: 'Thứ 3',
  WED: 'Thứ 4',
  THU: 'Thứ 5',
  FRI: 'Thứ 6',
  SAT: 'Thứ 7',
  SUN: 'Chủ nhật',
};

function getErrorMessage(error) {
  return error.response?.data?.message || error.message || 'Không thể tải học phần của bạn.';
}

function getScheduleText(schedule) {
  if (!schedule?.length) return 'Chưa có lịch học';
  return schedule
    .map((item) => {
      const room = item.room ? `, phòng ${item.room}` : '';
      return `${weekDays[item.day_of_week] || item.day_of_week}, tiết ${item.start_period}–${item.end_period}${room}`;
    })
    .join(' · ');
}

function getRegistrationStatus(status) {
  return status === 'ACTIVE' ? 'Đã đăng ký' : status;
}

export default function MyCourses() {
  const navigate = useNavigate();
  const [registrations, setRegistrations] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, total_pages: 1, total_items: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const loadRegistrations = useCallback(async (page = 1, refresh = false) => {
    setLoading(true);
    setRefreshing(refresh);
    setError('');
    try {
      const response = await getMyRegistrations({ page, pageSize: PAGE_SIZE, status: 'ACTIVE' });
      const data = response?.data;
      if (!Array.isArray(data?.items) || !data?.pagination) {
        throw new Error('Dữ liệu danh sách học phần không hợp lệ.');
      }

      const pageRegistrations = await Promise.all(
        data.items.map(async (registration) => {
          try {
            const detailResponse = await getCourseClass(registration.course_class_id);
            const course = detailResponse?.data?.course_class;
            if (!course) throw new Error('Dữ liệu chi tiết lớp học phần không hợp lệ.');
            return { ...registration, course, detailError: '' };
          } catch (detailRequestError) {
            return {
              ...registration,
              course: null,
              detailError: getErrorMessage(detailRequestError),
            };
          }
        }),
      );

      setRegistrations(pageRegistrations);
      setPagination(data.pagination);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
      setRegistrations([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadRegistrations(1);
  }, [loadRegistrations]);

  const page = pagination.page || 1;
  const totalPages = Math.max(1, pagination.total_pages || 1);

  return (
    <DashboardLayout role="STUDENT" pageTitle="Học phần của tôi">
      <div className="space-y-6">
        <div>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-red-700"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-red-600 text-white shadow-sm transition hover:bg-red-700">
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            </span>
            Quay lại
          </button>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-2xl font-bold text-gray-900">Danh sách học phần đã đăng ký</h2>
              
            </div>
            <button
              type="button"
              onClick={() => loadRegistrations(page, true)}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} aria-hidden="true" />
              Làm mới
            </button>
          </div>
        </div>

        {loading ? (
          <div className="space-y-3" role="status" aria-label="Đang tải học phần">
            {[1, 2, 3].map((item) => (
              <div key={item} className="h-28 animate-pulse rounded-lg border border-gray-100 bg-white" />
            ))}
            <span className="sr-only">Đang tải học phần đã đăng ký...</span>
          </div>
        ) : error ? (
          <div role="alert" className="rounded-lg border border-red-200 bg-white p-8 text-center">
            <p className="font-medium text-gray-900">Không thể tải học phần</p>
            <p className="mt-2 text-sm text-red-700">{error}</p>
            <button
              type="button"
              onClick={() => loadRegistrations(page, true)}
              className="mt-4 inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Thử lại
            </button>
          </div>
        ) : registrations.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white px-6 py-14 text-center">
            <BookOpen className="mx-auto h-10 w-10 text-gray-300" aria-hidden="true" />
            <p className="mt-4 font-medium text-gray-900">Bạn chưa đăng ký học phần nào</p>
            <p className="mt-1 text-sm text-gray-500">Các lớp đã đăng ký sẽ xuất hiện tại đây.</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full min-w-225 table-fixed border-collapse text-sm">
                <thead className="bg-gray-50 text-xs font-semibold text-gray-700">
                  <tr>
                    <th scope="col" className="w-14 border-b border-r border-gray-200 px-3 py-3 text-center">TT</th>
                    <th scope="col" className="w-32 border-b border-r border-gray-200 px-4 py-3 text-left">Mã HP</th>
                    <th scope="col" className="w-56 border-b border-r border-gray-200 px-4 py-3 text-left">Tên học phần</th>
                    <th scope="col" className="w-16 border-b border-r border-gray-200 px-3 py-3 text-center">STC</th>
                    <th scope="col" className="w-40 border-b border-r border-gray-200 px-4 py-3 text-left">Mã lớp</th>
                    <th scope="col" className="min-w-[320px] border-b border-r border-gray-200 px-4 py-3 text-left">
                      Thông tin lịch học
                    </th>
                    <th scope="col" className="w-32 border-b border-gray-200 px-4 py-3 text-center">Trạng thái</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 text-gray-700">
                  {registrations.map((registration, index) => (
                    <tr key={registration.registration_id} className="transition-colors hover:bg-red-50/40">
                      <td className="border-r border-gray-200 px-3 py-4 text-center text-gray-500">
                        {(page - 1) * (pagination.page_size || PAGE_SIZE) + index + 1}
                      </td>
                      <td className="border-r border-gray-200 px-4 py-4 font-medium text-red-700">
                        {registration.course?.course_code || '—'}
                      </td>
                      <td className="border-r border-gray-200 px-4 py-4 font-medium text-gray-900">
                        {registration.course_name || registration.course?.course_name || '—'}
                      </td>
                      <td className="border-r border-gray-200 px-3 py-4 text-center">
                        {registration.credits ?? '—'}
                      </td>
                      <td className="border-r border-gray-200 px-4 py-4">
                        {registration.course?.class_code || registration.class_code || '—'}
                      </td>
                      <td
                        className={`border-r border-gray-200 px-4 py-4 leading-6 ${
                          registration.detailError ? 'text-amber-700' : ''
                        }`}
                        title={registration.detailError || undefined}
                      >
                        {registration.detailError
                          ? 'Không thể tải lịch học'
                          : getScheduleText(registration.course?.schedule)}
                      </td>
                      <td className="px-4 py-4 text-center">
                        <span className="inline-flex whitespace-nowrap rounded border border-green-200 bg-green-50 px-2 py-1 text-xs font-medium text-green-700">
                          {getRegistrationStatus(registration.status)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <nav
                aria-label="Phân trang học phần của tôi"
                className="flex items-center justify-end gap-1 border-t border-gray-200 px-2 py-2"
              >
                <button
                  type="button"
                  onClick={() => loadRegistrations(Math.max(1, page - 1))}
                  disabled={page <= 1 || loading}
                  aria-label="Trang trước"
                  className="flex h-8 w-8 items-center justify-center rounded text-gray-600 hover:bg-white hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                </button>
                {Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => (
                  <button
                    type="button"
                    key={pageNumber}
                    onClick={() => loadRegistrations(pageNumber)}
                    aria-label={`Trang ${pageNumber}`}
                    aria-current={pageNumber === page ? 'page' : undefined}
                    disabled={loading}
                    className={`h-8 min-w-8 rounded px-2 text-xs font-medium ${
                      pageNumber === page ? 'bg-red-600 text-white' : 'text-gray-600 hover:bg-white hover:text-red-700'
                    }`}
                  >
                    {pageNumber}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => loadRegistrations(Math.min(totalPages, page + 1))}
                  disabled={page >= totalPages || loading}
                  aria-label="Trang sau"
                  className="flex h-8 w-8 items-center justify-center rounded text-gray-600 hover:bg-white hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" aria-hidden="true" />
                </button>
              </nav>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
