import { useState, useEffect, useRef } from 'react';
import { syncResources as syncControlApi, getControlSyncStatus } from '../api/control';
import { triggerSync as syncInventoryApi, getInventorySyncStatus } from '../api/inventory';
import { toast } from 'sonner';

export const useControlSync = (account) => {
    const [syncing, setSyncing] = useState(false);

    const prevSyncing = useRef(syncing);
    const syncMessage = useRef(null);

    useEffect(() => {
        if (!account) return;
        const check = async () => {
            try {
                const res = await getControlSyncStatus(account);
                setSyncing(res.is_syncing);
                if (res.message) {
                    syncMessage.current = res.message;
                }
            } catch(e) {}
        };
        let interval;
        if (syncing) {
            // Delay first poll to allow POST request to reach server
            interval = setInterval(check, 3000);
        } else {
            check();
            interval = setInterval(check, 15000);
        }
        return () => clearInterval(interval);
    }, [account, syncing]);

    useEffect(() => {
        if (prevSyncing.current && !syncing) {
            const msg = syncMessage.current || "Control sync completed successfully!";
            if (msg.toLowerCase().startsWith("failed") || msg.toLowerCase().startsWith("error") || msg.toLowerCase().startsWith("fatal")) {
                toast.error(msg);
            } else {
                toast.success(msg);
            }
            syncMessage.current = null;
            // Notify UI to refresh data now that the background sync has ACTUALLY completed
            window.dispatchEvent(new Event('app:refresh-data'));
        }
        prevSyncing.current = syncing;
    }, [syncing]);

    const startControlSync = async (accountName, region = 'all', onSuccess, onError) => {
        if (syncing) return;
        setSyncing(true);
        try {
            await syncControlApi(accountName || account, region);
            const regionLabel = (!region || region === 'all')
                ? 'All Regions'
                : region.includes(',')
                ? `${region.split(',').length} regions`
                : region;
            toast.info(`Control sync started for ${regionLabel}...`);
            if (onSuccess) onSuccess();
        } catch(e) {
            setSyncing(false);
            toast.error("Failed to start sync");
            if (onError) onError(e);
        }
    };

    return { syncing, startControlSync };
};

export const useInventorySync = (account, provider, configId) => {
    const [syncing, setSyncing] = useState(false);

    const prevSyncing = useRef(syncing);
    const syncMessage = useRef(null);

    useEffect(() => {
        if (!account) return;
        const check = async () => {
            try {
                const res = await getInventorySyncStatus(account);
                setSyncing(res.is_syncing);
                if (res.message) {
                    syncMessage.current = res.message;
                }
            } catch(e) {}
        };
        let interval;
        if (syncing) {
            // Delay first poll to allow POST request to reach server
            interval = setInterval(check, 3000);
        } else {
            check();
            interval = setInterval(check, 15000);
        }
        return () => clearInterval(interval);
    }, [account, syncing]);

    useEffect(() => {
        if (prevSyncing.current && !syncing) {
            const msg = syncMessage.current || "Inventory sync completed successfully!";
            if (msg.toLowerCase().startsWith("failed") || msg.toLowerCase().startsWith("error") || msg.toLowerCase().startsWith("fatal")) {
                toast.error(msg);
            } else {
                toast.success(msg);
            }
            syncMessage.current = null;
        }
        prevSyncing.current = syncing;
    }, [syncing]);

    const startInventorySync = async (providerName, configIdNum, onSuccess, onError) => {
        if (syncing) return;
        setSyncing(true);
        try {
            await syncInventoryApi(providerName || provider, configIdNum || configId);
            toast.info("Inventory sync started in the background...");
            if (onSuccess) onSuccess();
        } catch(e) {
            setSyncing(false);
            toast.error("Failed to start sync");
            if (onError) onError(e);
        }
    };

    return { syncing, startInventorySync };
};
