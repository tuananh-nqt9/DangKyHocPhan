import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GraduationCap, Lock, User, Eye, EyeOff, LogIn, AlertCircle } from 'lucide-react';
import { login, saveAuthData } from '../../services/authService';

export default function Login() {
  const navigate = useNavigate();

  const [studentId, setStudentId] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('STUDENT');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    // Client-side validation
    if (!studentId.trim()) {
      setError('Vui lòng nhập mã sinh viên / quản trị viên.');
      return;
    }
    if (!password) {
      setError('Vui lòng nhập mật khẩu.');
      return;
    }
    if (password.length < 8 || password.length > 128) {
      setError('Mật khẩu phải có độ dài từ 8 đến 128 ký tự.');
      return;
    }

    setLoading(true);
    try {
      const result = await login(studentId.trim(), password);
      const userData = result.data;
      const userRole = userData?.student?.role;

      if (!userData?.student || !['STUDENT', 'ADMIN'].includes(userRole)) {
        setError('Phản hồi đăng nhập không hợp lệ. Vui lòng thử lại.');
        return;
      }

      // Verify role matches selection
      if (userRole !== role) {
        setError(
          role === 'ADMIN'
            ? 'Tài khoản này không có quyền quản trị viên.'
            : 'Tài khoản này là quản trị viên. Vui lòng chọn vai trò Admin.',
        );
        setLoading(false);
        return;
      }

      saveAuthData(userData);

      // Redirect based on role
      if (userRole === 'ADMIN') {
        navigate('/admin/dashboard');
      } else {
        navigate('/student/dashboard');
      }
    } catch (err) {
      const apiError = err.response?.data;
      if (apiError?.code === 'UNAUTHORIZED' || apiError?.code === 'INVALID_CREDENTIALS') {
        setError('Sai mã sinh viên hoặc mật khẩu. Vui lòng thử lại.');
      } else if (apiError?.code === 'VALIDATION_ERROR') {
        const fieldErrors = apiError.errors?.map((e) => e.message).join('. ');
        setError(fieldErrors || 'Dữ liệu không hợp lệ.');
      } else if (apiError?.code === 'RATE_LIMITED') {
        setError('Bạn đã thử quá nhiều lần. Vui lòng đợi một lát rồi thử lại.');
      } else if (err.code === 'ERR_NETWORK') {
        setError('Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối mạng.');
      } else {
        setError(apiError?.message || 'Đã có lỗi xảy ra. Vui lòng thử lại.');
      }
    } finally {
      setLoading(false);
    }
  };

  const ssoAuthUrl = import.meta.env.VITE_SSO_AUTH_URL;

  return (
    <main className="relative min-h-screen bg-gradient-to-br from-primary-50 via-white to-primary-100 flex items-center justify-center px-4 py-8">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary-200/30 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-primary-300/20 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Logo / Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-primary-600 rounded-2xl shadow-lg shadow-primary-500/30 mb-4">
            <GraduationCap className="w-9 h-9 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Đăng ký Học phần PTIT</h1>
          <p className="text-gray-500 mt-1 text-sm">Đăng nhập để tiếp tục đăng ký học phần</p>
        </div>

        {/* Login Card */}
        <div className="bg-white rounded-2xl shadow-xl shadow-primary-500/5 border border-gray-100 p-8">
          {/* Role Toggle */}
          <div className="flex bg-gray-100 rounded-xl p-1 mb-3" role="group" aria-label="Chọn vai trò đăng nhập">
            <button
              type="button"
              aria-pressed={role === 'STUDENT'}
              onClick={() => { setRole('STUDENT'); setError(''); }}
              disabled={loading}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                role === 'STUDENT'
                  ? 'bg-primary-600 text-white shadow-md shadow-primary-500/25'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <User className="w-4 h-4" />
              Sinh viên
            </button>
            <button
              type="button"
              aria-pressed={role === 'ADMIN'}
              onClick={() => { setRole('ADMIN'); setError(''); }}
              disabled={loading}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                role === 'ADMIN'
                  ? 'bg-primary-600 text-white shadow-md shadow-primary-500/25'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <Lock className="w-4 h-4" />
              Quản trị viên
            </button>
          </div>
          <p className="text-xs text-gray-500 mb-6 px-1">
            {role === 'ADMIN'
              ? 'Dành cho quản trị viên hệ thống.'
              : 'Dành cho sinh viên đăng ký và theo dõi học phần.'}
          </p>

          {/* Error Alert */}
          {error && (
            <div role="alert" aria-live="assertive" className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-6 text-sm animate-in">
              <AlertCircle className="w-5 h-5 mt-0.5 shrink-0 text-red-500" />
              <span>{error}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Student ID */}
            <div>
              <label htmlFor="studentId" className="block text-sm font-medium text-gray-700 mb-1.5">
                {role === 'ADMIN' ? 'Mã quản trị viên' : 'Mã sinh viên'}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                  <User className="w-5 h-5 text-gray-400" />
                </div>
                <input
                  id="studentId"
                  type="text"
                  value={studentId}
                  onChange={(e) => setStudentId(e.target.value.toUpperCase())}
                  placeholder={role === 'ADMIN' ? 'Nhập mã Admin...' : 'Nhập mã sinh viên...'}
                  required
                  autoComplete="username"
                  className="block w-full pl-11 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 focus:bg-white transition-all duration-200"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
                Mật khẩu
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                  <Lock className="w-5 h-5 text-gray-400" />
                </div>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Nhập mật khẩu"
                  required
                  maxLength={128}
                  autoComplete="current-password"
                  className="block w-full pl-11 pr-12 py-3 bg-gray-50 border border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 focus:bg-white transition-all duration-200"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                  aria-pressed={showPassword}
                  className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-primary-600 hover:bg-primary-700 active:bg-primary-800 disabled:bg-primary-400 text-white font-medium rounded-xl shadow-lg shadow-primary-500/25 hover:shadow-xl hover:shadow-primary-500/30 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-all duration-200 text-sm"
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Đang đăng nhập...
                </>
              ) : (
                <>
                  <LogIn className="w-5 h-5" />
                  Đăng nhập
                </>
              )}
            </button>
          </form>

          {/* SSO Divider */}
          {ssoAuthUrl && (
            <>
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="px-3 bg-white text-gray-400 uppercase tracking-wide">hoặc</span>
                </div>
              </div>

              {/* SSO Login Button */}
              <a
                href={ssoAuthUrl}
                className="w-full flex items-center justify-center gap-3 py-3 px-4 bg-white border border-gray-200 rounded-xl text-gray-700 font-medium hover:bg-gray-50 hover:border-gray-300 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-all duration-200 text-sm"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                    fill="#4285F4"
                  />
                  <path
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    fill="#34A853"
                  />
                  <path
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    fill="#FBBC05"
                  />
                  <path
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    fill="#EA4335"
                  />
                </svg>
                Đăng nhập bằng SSO (Google)
              </a>
            </>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-gray-400 mt-6">
          Hệ thống Đăng ký Học phần Trực tuyến &copy; 2026
        </p>
      </div>
    </main>
  );
}
