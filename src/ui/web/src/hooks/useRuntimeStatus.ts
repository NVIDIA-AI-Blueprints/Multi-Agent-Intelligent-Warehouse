import { useQuery } from '@tanstack/react-query';
import { runtimeAPI, RuntimeStatus } from '../services/api';

export function useRuntimeStatus() {
  return useQuery<RuntimeStatus>({
    queryKey: ['runtime-status'],
    queryFn: runtimeAPI.getStatus,
    refetchInterval: 30000,
    retry: 1,
    staleTime: 15000,
  });
}
