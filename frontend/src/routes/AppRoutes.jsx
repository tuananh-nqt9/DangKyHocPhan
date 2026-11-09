import { Navigate, Route, Routes } from 'react-router-dom';
import Login from '../pages/auth/Login.jsx';
import AdminDashboard from '../pages/admin/Dashboard.tsx';
import AdminCourseClasses from '../pages/admin/CourseClasses.tsx';
import AdminTesting from '../pages/admin/Testing.tsx';
import StudentDashboard from '../pages/student/Dashboard.jsx';
import MyCourses from '../pages/student/MyCourses.jsx';
import StudentRegistration from '../pages/student/Registration.jsx';
import { getUserRole, isAuthenticated } from '../services/authService.js';
import ProtectedRoute from './ProtectedRoute.jsx';
import RoleRoute from './RoleRoute.jsx';

function HomeRedirect() {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }

  const role = getUserRole();
  if (role === 'ADMIN') {
    return <Navigate to="/admin/dashboard" replace />;
  }
  if (role === 'STUDENT') {
    return <Navigate to="/student/dashboard" replace />;
  }

  return <Navigate to="/login" replace />;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<Login />} />
      <Route
        path="/student/dashboard"
        element={
          <ProtectedRoute>
            <RoleRoute role="STUDENT">
              <StudentDashboard />
            </RoleRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/student/registration"
        element={
          <ProtectedRoute>
            <RoleRoute role="STUDENT">
              <StudentRegistration />
            </RoleRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/student/my-courses"
        element={
          <ProtectedRoute>
            <RoleRoute role="STUDENT">
              <MyCourses />
            </RoleRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/dashboard"
        element={
          <ProtectedRoute>
            <RoleRoute role="ADMIN">
              <AdminDashboard />
            </RoleRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/course-classes"
        element={
          <ProtectedRoute>
            <RoleRoute role="ADMIN">
              <AdminCourseClasses />
            </RoleRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/testing"
        element={
          <ProtectedRoute>
            <RoleRoute role="ADMIN">
              <AdminTesting />
            </RoleRoute>
          </ProtectedRoute>
        }
      />
      <Route path="/admin/test-results" element={<Navigate to="/admin/testing?tab=results" replace />} />
      <Route path="*" element={<HomeRedirect />} />
    </Routes>
  );
}
