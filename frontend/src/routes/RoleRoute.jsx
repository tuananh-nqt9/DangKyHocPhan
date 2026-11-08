import { Navigate } from 'react-router-dom';
import { getUserRole } from '../services/authService.js';

export default function RoleRoute({ role, children }) {
  const userRole = getUserRole();

  if (userRole === role) {
    return children;
  }

  if (userRole === 'ADMIN') {
    return <Navigate to="/admin/dashboard" replace />;
  }
  if (userRole === 'STUDENT') {
    return <Navigate to="/student/dashboard" replace />;
  }

  return <Navigate to="/login" replace />;
}
