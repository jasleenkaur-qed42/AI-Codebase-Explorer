import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useClaudeSession } from './hooks/useClaudeSession';
import { Dashboard } from './pages/Dashboard';

const queryClient = new QueryClient();


function AppShell() {
  const { latestEvent} = useClaudeSession();

  return (
    <div style={{ display: 'flex', flex:1, height: '100vh' }}>
        <Dashboard event={latestEvent} />
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  );
}

export default App;
