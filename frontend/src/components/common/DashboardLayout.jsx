import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronDown, LogOut } from 'lucide-react';
import { clearAuthData, getCurrentUser, logout } from '../../services/authService.js';
import ptitLogo from '../../assets/ptitlogo.png';
import SiteFooter from './SiteFooter.jsx';

export default function DashboardLayout({ role, pageTitle, children, fixedViewport = false }) {
  const navigate = useNavigate();
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
      <header className="shrink-0 border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
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
          {isAdmin && (
            <h1 className="mr-auto text-base font-semibold text-gray-900">{title}</h1>
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

      <section
        className={`mx-auto w-full max-w-6xl ${
          fixedViewport
            ? 'flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain px-4 py-5 sm:px-6'
            : 'flex-1 px-4 py-10 sm:px-6'
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
      <SiteFooter />
    </main>
  );
}
