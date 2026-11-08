import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GraduationCap, LogOut, ShieldCheck } from 'lucide-react';
import { clearAuthData, getCurrentUser, logout } from '../../services/authService.js';

export default function DashboardLayout({ role }) {
  const navigate = useNavigate();
  const user = getCurrentUser();
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState('');
  const isAdmin = role === 'ADMIN';

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
    <main className="min-h-screen bg-gray-50">
      <header className="border-b border-red-100 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-600 text-white">
              {isAdmin ? <ShieldCheck className="h-5 w-5" /> : <GraduationCap className="h-6 w-6" />}
            </div>
            <div>
              <p className="font-semibold text-gray-900">Đăng ký Học phần PTIT</p>
              <p className="text-xs text-gray-500">{isAdmin ? 'Cổng quản trị viên' : 'Cổng sinh viên'}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            disabled={loggingOut}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 transition hover:border-red-200 hover:bg-red-50 hover:text-primary-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <LogOut className="h-4 w-4" />
            {loggingOut ? 'Đang đăng xuất...' : 'Đăng xuất'}
          </button>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        {error && (
          <div role="alert" className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
        <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm sm:p-8">
          <p className="text-sm font-medium text-primary-700">
            {isAdmin ? 'Khu vực quản trị' : 'Khu vực sinh viên'}
          </p>
          <h1 className="mt-2 text-2xl font-bold text-gray-900">
            Xin chào, {user?.full_name || user?.student_id}
          </h1>
          <p className="mt-2 text-sm text-gray-600">
            {isAdmin
              ? 'Bạn đã đăng nhập với quyền quản trị viên.'
              : 'Bạn đã đăng nhập thành công. Chào mừng bạn đến với hệ thống đăng ký học phần.'}
          </p>
          <div className="mt-6 inline-flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            <span className="font-medium">Mã tài khoản:</span>
            <span>{user?.student_id}</span>
          </div>
        </div>
      </section>
    </main>
  );
}
