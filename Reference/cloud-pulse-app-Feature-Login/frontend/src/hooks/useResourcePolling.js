import { useEffect } from 'react';
import { toast } from 'sonner';
import { getDbState } from '../api/control';

export function useResourcePolling(resources, setResources) {
  useEffect(() => {
    const interval = setInterval(() => {
      const transitioningResources = resources.filter(r =>
        !['RUNNING', 'STOPPED', 'UNKNOWN', 'TERMINATED', 'ACTIVE', 'AVAILABLE'].includes(r.status.toUpperCase())
      );
  
      if (transitioningResources.length === 0) return;
      
      const uniqueResources = Array.from(new Map(transitioningResources.map(r => [r.resource_id, r])).values());
  
      uniqueResources.forEach(async (r) => {
        try {
          const liveData = await getDbState(r.resource_id);
  
          if (liveData.status && liveData.status.toUpperCase() !== r.status.toUpperCase()) {
            const newState = liveData.status.toUpperCase();
            const oldState = r.status.toUpperCase();
  
            if (oldState === 'STOPPING' && newState === 'RUNNING') return;
            if (oldState === 'STARTING' && newState === 'STOPPED') return;
  
            if (oldState !== 'RUNNING' && newState === 'RUNNING') {
              toast.success(`Resource ${r.name || r.resource_id} is completely ON!`);
              // Dispatch refresh to fetch any newly discovered child resources
              window.dispatchEvent(new Event('app:refresh-data'));
            } else if (oldState !== 'STOPPED' && newState === 'STOPPED' && newState !== 'TERMINATED') {
              toast.success(`Resource ${r.name || r.resource_id} is completely OFF!`);
              // Dispatch refresh to remove any cleaned-up child resources
              window.dispatchEvent(new Event('app:refresh-data'));
            }
  
            setResources(prev => prev.map(res =>
              res.resource_id === r.resource_id ? { ...res, status: newState } : res
            ));
          }
        } catch (e) {
          console.error(`Failed to poll state for ${r.resource_id}`, e);
          if (e.response && e.response.status === 404) {
             // Resource has been deleted from the database (e.g. terminated EC2)
             setResources(prev => prev.filter(res => res.resource_id !== r.resource_id));
          }
        }
      });
    }, 10000); // 10 seconds

    return () => clearInterval(interval);
  }, [resources, setResources]);
}
