import { Navigate } from 'react-router-dom';
import { getCurrentUser, isAuthenticated } from '../services/authService.js';

export default function ProtectedRoute({ children }) {
  if (!isAuthenticated() || !getCurrentUser()) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
