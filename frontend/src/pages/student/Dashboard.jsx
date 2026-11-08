import { useCallback, useEffect, useState } from 'react';
import DashboardLayout from '../../components/common/DashboardLayout.jsx';
import RegistrationShortcut from '../../components/student/RegistrationShortcut.jsx';
import RegistrationStatsCard from '../../components/student/RegistrationStatsCard.jsx';
import StudentInfoCard from '../../components/student/StudentInfoCard.jsx';
import { getCurrentUser, isAuthenticated } from '../../services/authService.js';
import { getMyRegistrations } from '../../services/registrationService.js';

export default function StudentDashboard() {
  const user = getCurrentUser();
  const [registrationCount, setRegistrationCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadRegistrationCount = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const response = await getMyRegistrations({ page: 1, pageSize: 1, status: 'ACTIVE' });
      const count = response?.data?.pagination?.total_items;

      if (!Number.isInteger(count) || count < 0) {
        throw new Error('Dữ liệu đăng ký nhận được không hợp lệ.');
      }

      setRegistrationCount(count);
    } catch (requestError) {
      setError(
        requestError.response?.data?.message ||
          requestError.message ||
          'Không thể tải thông tin học phần đã đăng ký.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRegistrationCount();
  }, [loadRegistrationCount]);

  return (
    <DashboardLayout role="STUDENT">
      <div className="space-y-6">
        <div className="grid items-stretch gap-6 md:grid-cols-2">
          <StudentInfoCard user={user} sessionActive={isAuthenticated()} />
          <RegistrationStatsCard
            count={registrationCount}
            loading={loading}
            error={error}
            onRetry={loadRegistrationCount}
          />
        </div>
        <RegistrationShortcut />
      </div>
    </DashboardLayout>
  );
}
