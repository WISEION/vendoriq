import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import { SessionProvider } from '../auth/SessionProvider';
import { LocaleProvider } from '../i18n/LocaleProvider';
import { ThemeProvider } from '../theme/ThemeProvider';
import { queryClient } from './queryClient';
import { router } from './routes';

// Server state is owned by TanStack Query; there is no client-side data store, because
// there is no client-side business logic to keep state for.
export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <LocaleProvider>
          <SessionProvider>
            <RouterProvider router={router} />
          </SessionProvider>
        </LocaleProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
