import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../api/client';

/**
 * Brief §6: while `AUTH_MODE=test` the one-time codes are visible and the accounts are seeded.
 * That has to be impossible to miss, so the shell says so on every screen.
 */
export function DevBanner() {
  const { data } = useQuery({ queryKey: ['health'], queryFn: getHealth, retry: false });
  if (!data || data.auth_mode !== 'test') return null;

  return (
    <div className="banner" role="status">
      <strong>AUTH_MODE=test</strong>
      <span>
        Seeded test accounts are active and one-time codes are shown in the server log —
        {' '}
        {data.app_env} / storage: {data.storage_backend}
      </span>
    </div>
  );
}
