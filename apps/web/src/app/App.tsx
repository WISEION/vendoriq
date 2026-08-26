import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import { LocaleProvider } from '../i18n/LocaleProvider';
import { ThemeProvider } from '../theme/ThemeProvider';
import { router } from './routes';

// Server state is owned by TanStack Query; there is no client-side data store, because
// there is no client-side business logic to keep state for.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <LocaleProvider>
          <RouterProvider router={router} />
        </LocaleProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
