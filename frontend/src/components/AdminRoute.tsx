import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

const ADMIN_ROLES = ['content_admin', 'super_admin'];

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  if (!user || !ADMIN_ROLES.includes(user.role)) {
    return <Navigate to='/' replace />;
  }
  return <>{children}</>;
}
