import { useQuery } from '@tanstack/react-query';
import { demoAPI, DemoStatus } from '../services/demoAPI';

const POLL_MS = 3000;

export interface DemoState {
  isDemoMode: boolean;
  status: DemoStatus | null;
  isLoading: boolean;
  refetch: () => void;
}

export function useDemoStatus(): DemoState {
  const { data, isLoading, refetch } = useQuery<DemoStatus | null>({
    queryKey: ['demo-status'],
    queryFn: demoAPI.getStatusSafe,
    refetchInterval: POLL_MS,
    retry: 1,
    staleTime: POLL_MS,
  });

  return {
    isDemoMode: data != null && data !== undefined,
    status: data ?? null,
    isLoading,
    refetch,
  };
}
