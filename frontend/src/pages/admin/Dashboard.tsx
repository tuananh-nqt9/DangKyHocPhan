import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, ArrowRight, BookOpen, CheckCircle2, CircleAlert, RefreshCw, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import DashboardLayout from '../../components/common/DashboardLayout.jsx';
import { getAdminHealth, getAllAdminCourseClasses } from '../../services/adminService';
import type { CourseClass, HealthData } from '../../services/adminTypes';

function getErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = error.response;
    if (typeof response === 'object' && response !== null && 'data' in response) {
      const data = response.data;
      if (typeof data === 'object' && data !== null && 'message' in data && typeof data.message === 'string') {
        return data.message;
      }
    }
  }
  return error instanceof Error ? error.message : 'Không thể tải dữ liệu quản trị.';
}

function StatCard({
  label,
  value,
  hint,
  Icon,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  Icon: typeof BookOpen;
  tone: 'red' | 'green' | 'gray' | 'blue';
}) {
  const tones = {
    red: 'bg-red-50 text-red-700',
    green: 'bg-green-50 text-green-700',
    gray: 'bg-gray-100 text-gray-700',
    blue: 'bg-blue-50 text-blue-700',
  };
  return (
    <article className="rounded-none border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900">{value}</p>
        </div>
        <span className={`flex h-10 w-10 items-center justify-center rounded-none ${tones[tone]}`}>
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
      </div>
      <p className="mt-3 text-xs text-gray-500">{hint}</p>
    </article>
  );
}

function FeatureStatus({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-gray-100 py-3 last:border-0">
      <span className="text-sm text-gray-700">{label}</span>
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium ${
        enabled ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600'
      }`}>
        {enabled ? <CheckCircle2 className="h-3.5 w-3.5" /> : <CircleAlert className="h-3.5 w-3.5" />}
        {enabled ? 'Đang bật' : 'Đang tắt'}
      </span>
    </div>
  );
}

export default function AdminDashboard() {
  const [courses, setCourses] = useState<CourseClass[]>([]);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [courseError, setCourseError] = useState('');
  const [healthError, setHealthError] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setCourseError('');
    setHealthError('');
    const [courseResult, healthResult] = await Promise.allSettled([
      getAllAdminCourseClasses(),
      getAdminHealth(),
    ]);

    if (courseResult.status === 'fulfilled') {
      setCourses(courseResult.value);
    } else {
      setCourseError(getErrorMessage(courseResult.reason));
    }
    if (healthResult.status === 'fulfilled') {
      setHealth(healthResult.value);
    } else {
      setHealthError(getErrorMessage(healthResult.reason));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.allSettled([getAllAdminCourseClasses(), getAdminHealth()]).then(([courseResult, healthResult]) => {
      if (!active) return;
      if (courseResult.status === 'fulfilled') setCourses(courseResult.value);
      else setCourseError(getErrorMessage(courseResult.reason));
      if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
      else setHealthError(getErrorMessage(healthResult.reason));
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, []);

  const stats = useMemo(() => {
    const open = courses.filter((course) => course.status === 'OPEN').length;
    const closed = courses.length - open;
    const capacity = courses.reduce((total, course) => total + course.capacity, 0);
    const registered = courses.reduce((total, course) => total + course.registered_count, 0);
    const remaining = courses.reduce((total, course) => total + course.remaining_seats, 0);
    return { open, closed, capacity, registered, remaining };
  }, [courses]);

  const featuredCourses = useMemo(
    () => [...courses].sort((a, b) => b.registered_count - a.registered_count).slice(0, 5),
    [courses],
  );

  return (
    <DashboardLayout role="ADMIN" pageTitle="Dashboard" stickyHeader>
      <div className="space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-red-700">Tổng quan hệ thống</p>
           
          </div>
          <button
            type="button"
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center gap-2 border border-gray-200 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
            Làm mới
          </button>
        </div>

        {courseError && (
          <div role="alert" className="border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Không thể tải thống kê lớp học phần: {courseError}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {loading && courses.length === 0
            ? Array.from({ length: 6 }, (_, index) => (
              <div key={index} className="h-36 animate-pulse border border-gray-100 bg-white" />
            ))
            : <>
              <StatCard label="Tổng số lớp học phần" value={String(courses.length)} hint="Tất cả lớp học phần" Icon={BookOpen} tone="red" />
              <StatCard label="Lớp đang mở" value={String(stats.open)} hint="Có thể đăng ký" Icon={Activity} tone="green" />
              <StatCard label="Lớp đã đóng" value={String(stats.closed)} hint="Không nhận đăng ký mới" Icon={CircleAlert} tone="gray" />
              <StatCard label="Tổng sức chứa" value={stats.capacity.toLocaleString('vi-VN')} hint="Tổng số chỗ của các lớp" Icon={Users} tone="blue" />
              <StatCard label="Đã đăng ký" value={stats.registered.toLocaleString('vi-VN')} hint="Tổng lượt đăng ký hiện tại" Icon={CheckCircle2} tone="green" />
              <StatCard label="Chỗ còn trống" value={stats.remaining.toLocaleString('vi-VN')} hint="Tổng chỗ chưa được đăng ký" Icon={Users} tone="red" />
            </>}
        </div>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,0.8fr)]">
          <section className="overflow-hidden border border-gray-200 bg-white shadow-sm">
            <div className="flex items-center justify-between gap-4 border-b border-gray-100 px-5 py-4">
              <div>
                <h3 className="font-semibold text-gray-900">Lớp học phần nổi bật</h3>
                <p className="mt-1 text-xs text-gray-500">Xếp theo số lượng đăng ký từ API.</p>
              </div>
              <Link to="/admin/course-classes" className="inline-flex items-center gap-1 text-sm font-semibold text-red-700 hover:text-red-800">
                Quản lý lớp <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
            {loading && courses.length === 0 ? (
              <div className="space-y-4 p-5" aria-label="Đang tải lớp học phần">
                {[1, 2, 3].map((item) => <div key={item} className="h-12 animate-pulse bg-gray-100" />)}
              </div>
            ) : featuredCourses.length ? (
              <div className="divide-y divide-gray-100">
                {featuredCourses.map((course) => {
                  const ratio = course.capacity ? Math.min(100, (course.registered_count / course.capacity) * 100) : 0;
                  return (
                    <div key={course.course_class_id} className="px-5 py-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">{course.course_name}</p>
                          <p className="mt-1 text-xs text-gray-500">{course.class_code} · {course.course_code}</p>
                        </div>
                        <span className="text-xs font-medium text-gray-600">
                          {course.registered_count}/{course.capacity} chỗ
                        </span>
                      </div>
                      <div className="mt-3 h-2 overflow-hidden bg-gray-100">
                        <div className="h-full bg-red-600 transition-all" style={{ width: `${ratio}%` }} />
                      </div>
                      <p className="mt-1 text-right text-xs text-gray-500">{ratio.toFixed(0)}% đã đăng ký</p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="px-5 py-10 text-center text-sm text-gray-500">Chưa có dữ liệu lớp học phần.</p>
            )}
          </section>

          <div>
            <section className="border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-gray-900">Trạng thái hệ thống</h3>
                  <p className="mt-1 text-xs text-gray-500">
                    {health?.api_version ? `API v${health.api_version}` : 'Thông tin từ /health'}
                  </p>
                </div>
                <Activity className="h-5 w-5 text-red-600" aria-hidden="true" />
              </div>
              {healthError ? (
                <p role="alert" className="mt-4 bg-amber-50 p-3 text-sm text-amber-800">{healthError}</p>
              ) : health ? (
                <div className="mt-3">
                  <FeatureStatus label="API" enabled={health.status === 'UP'} />
                  <FeatureStatus label="Cơ sở dữ liệu" enabled={health.database === 'UP'} />
                </div>
              ) : (
                <p className="mt-4 text-sm text-gray-500">{loading ? 'Đang tải trạng thái...' : 'Chưa có dữ liệu trạng thái.'}</p>
              )}
            </section>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
