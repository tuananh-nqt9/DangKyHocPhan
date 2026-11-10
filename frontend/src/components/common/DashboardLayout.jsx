import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { BookOpen, ChevronDown, FlaskConical, LayoutDashboard, LogOut } from 'lucide-react';
import { clearAuthData, getCurrentUser, logout } from '../../services/authService.js';
import ptitLogo from '../../assets/ptitlogo.png';
import SiteFooter from './SiteFooter.jsx';

export default function DashboardLayout({
  role,
  pageTitle,
  children,
  fixedViewport = false,
  stickyHeader = false,
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const user = getCurrentUser();
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState('');
  const isAdmin = role === 'ADMIN';
  const title = pageTitle || (isAdmin ? 'Trang quản trị' : 'Trang chủ sinh viên');
  const displayName = user?.full_name || user?.student_id || '';
  const avatarInitial = (displayName.trim().charAt(0) || '?').toLocaleUpperCase('vi');

  const handleLogout = async () => {
    setError('');
    setLoggingOut(true);

    try {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        await logout(refreshToken);
      }
      clearAuthData();
      navigate('/login', { replace: true });
    } catch (err) {
      setError(
        err.response?.data?.message ||
          'Không thể kết thúc phiên đăng nhập. Vui lòng thử lại.',
      );
    } finally {
      setLoggingOut(false);
    }
  };

  return (
    <main className={`${fixedViewport ? 'flex h-screen flex-col overflow-hidden' : 'flex min-h-screen flex-col'} bg-gray-50`}>
      <header className={`shrink-0 border-b border-gray-200 bg-white ${stickyHeader ? 'sticky top-0 z-30' : ''}`}>
        <div className="flex w-full flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          {isAdmin ? (
            <div className="flex min-w-0 items-center gap-3">
              <img
                src={ptitLogo}
                alt="Logo PTIT"
                className="h-12 w-12 rounded-xl border border-red-100 bg-white object-contain"
              />
              <div className="min-w-0">
                <p className="font-semibold text-gray-900">Đăng ký Học phần PTIT</p>
                <p className="text-xs text-gray-500">Cổng quản trị viên</p>
              </div>
            </div>
          ) : (
            <Link
              to="/student/dashboard"
              aria-label="Về trang chủ sinh viên"
              className="flex min-w-0 items-center gap-3 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-red-600"
            >
            <img
              src={ptitLogo}
              alt="Logo PTIT"
              className="h-12 w-12 rounded-xl border border-red-100 bg-white object-contain"
            />
            <div className="min-w-0">
              <p className="font-semibold text-gray-900">Đăng ký Học phần PTIT</p>
              <p className="text-xs text-gray-500">Cổng sinh viên</p>
            </div>
            </Link>
          )}
          <details className="group relative">
            <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl p-1.5 outline-none hover:bg-gray-50 focus-visible:ring-2 focus-visible:ring-red-600">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-red-50 text-sm font-semibold text-red-700">
                {avatarInitial}
              </span>
              <span className="hidden max-w-36 truncate text-sm font-medium text-gray-700 sm:block">
                {displayName}
              </span>
              <ChevronDown className="h-4 w-4 text-gray-400" aria-hidden="true" />
              <span className="sr-only">Mở menu tài khoản</span>
            </summary>
            <div className="absolute right-0 z-10 mt-2 w-64 rounded-xl border border-gray-200 bg-white p-3 shadow-lg">
              <p className="truncate text-sm font-semibold text-gray-900">{displayName}</p>
              <p className="mt-1 text-xs text-gray-500">{user?.student_id}</p>
              <p className="mt-1 text-xs text-gray-500">{isAdmin ? 'Quản trị viên' : 'Sinh viên'}</p>
              <div className="my-3 border-t border-gray-100" />
              <button
                type="button"
                onClick={handleLogout}
                disabled={loggingOut}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium text-gray-700 transition hover:bg-red-50 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
                {loggingOut ? 'Đang đăng xuất...' : 'Đăng xuất'}
              </button>
            </div>
          </details>
        </div>
      </header>

      <div className={isAdmin ? 'flex w-full flex-1 flex-col md:flex-row' : 'flex flex-1 flex-col'}>
        {isAdmin && (
          <aside className="shrink-0 border-b border-gray-200 bg-white md:w-52 md:border-b-0 md:border-r">
            <nav aria-label="Điều hướng quản trị" className="flex gap-1 overflow-x-auto p-2 md:sticky md:top-0 md:flex-col md:gap-0 md:p-2">
              {[
                { to: '/admin/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
                { to: '/admin/course-classes', label: 'Quản lý lớp học phần', Icon: BookOpen },
                { to: '/admin/testing', label: 'Trung tâm kiểm thử', Icon: FlaskConical },
              ].map(({ to, label, Icon }) => {
                const active = location.pathname === to ||
                  (to === '/admin/testing' && location.pathname === '/admin/test-results');
                return (
                  <Link
                    key={to}
                    to={to}
                    aria-current={active ? 'page' : undefined}
                    className={`inline-flex shrink-0 items-center gap-2.5 border-l-2 px-2.5 py-2 text-[13px] font-medium transition md:w-full ${
                      active
                        ? 'border-red-600 bg-red-50 text-red-700'
                        : 'border-transparent text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                    }`}
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </aside>
        )}
        <section
          className={`${isAdmin ? 'min-w-0 flex-1' : 'mx-auto w-full max-w-6xl'} ${
            fixedViewport
              ? 'flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain px-4 py-5 sm:px-6'
              : isAdmin
                ? 'flex-1 px-4 py-6 sm:px-6 sm:py-8'
                : 'flex-1 px-4 py-8 sm:px-6 sm:py-10'
          }`}
        >
          {error && (
            <div role="alert" className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
          {children || (
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
              <p className="text-sm font-medium text-red-700">Khu vực quản trị</p>
              <h2 className="mt-2 text-2xl font-bold text-gray-900">
                Xin chào, {displayName}
              </h2>
              <p className="mt-2 text-sm text-gray-600">
                Bạn đã đăng nhập với quyền quản trị viên.
              </p>
              <div className="mt-6 inline-flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
                <span className="font-medium">Mã tài khoản:</span>
                <span>{user?.student_id}</span>
              </div>
            </div>
          )}
        </section>
      </div>
      <SiteFooter />
    </main>
  );
}
