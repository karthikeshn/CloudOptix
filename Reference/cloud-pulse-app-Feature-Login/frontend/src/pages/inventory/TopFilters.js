import React from 'react';
import { FilterBar } from '../../components/ui/FilterBar';

export default function TopFilters({ topFilters, setTopFilters, selectedAccount, setSelectedAccount, accounts, availableRegions, availableLinked, availableTags }) {
  const uniqueProviders = [...new Set(accounts.map(a => (a.provider || '').toUpperCase()))].sort();
  const providerOptions = uniqueProviders.map(p => ({label: p, value: p}));

  const handleProviderChange = (newProvider) => {
    setTopFilters({...topFilters, provider: newProvider});
    const filtered = accounts.filter(a => (a.provider || '').toUpperCase() === newProvider);
    
    if (filtered.length > 0 && !filtered.find(a => a.account_name === selectedAccount)) {
      setSelectedAccount(filtered[0].account_name);
    } else if (filtered.length === 0) {
      setSelectedAccount('');
    }
  };

  const filteredAccounts = accounts.filter(a => (a.provider || '').toUpperCase() === topFilters.provider);

  let linkedLabel = "Linked:";
  let linkedOptionAll = "All Accounts";
  if (topFilters.provider === "AWS") {
    linkedLabel = "Linked Account:";
    linkedOptionAll = "All Accounts";
  } else if (topFilters.provider === "AZURE") {
    linkedLabel = "Subscription:";
    linkedOptionAll = "All Subscriptions";
  } else if (topFilters.provider === "GCP") {
    linkedLabel = "Project:";
    linkedOptionAll = "All Projects";
  }

  const filters = [
    { label: "Provider:", value: topFilters.provider, onChange: handleProviderChange, options: providerOptions, width: "w-auto" },
    { label: "Account:", value: selectedAccount, onChange: setSelectedAccount, options: filteredAccounts.map(a => ({label: a.account_name, value: a.account_name})), width: "max-w-[150px]" },
    { label: "Region:", value: topFilters.region, onChange: v => setTopFilters({...topFilters, region: v}), options: [{label: 'All Regions', value: 'All Regions'}, ...availableRegions.map(r => ({label: r, value: r}))], width: "max-w-[120px]" },
    { label: linkedLabel, value: topFilters.linked, onChange: v => setTopFilters({...topFilters, linked: v}), options: [{label: linkedOptionAll, value: 'All Accounts'}, ...availableLinked.map(l => ({label: l, value: l}))], width: "max-w-[160px]" },
    { label: "Tag:", value: topFilters.tag, onChange: v => setTopFilters({...topFilters, tag: v}), options: [{label: 'All', value: 'All'}, ...availableTags.map(t => ({label: t, value: t}))], width: "max-w-[120px]" },
    { 
      label: "Range:", 
      value: topFilters.range, 
      onChange: v => setTopFilters({...topFilters, range: v}), 
      options: [
        {label: 'Today', value: 1}, 
        {label: 'Last 7 days', value: 7}, 
        {label: 'Last 14 days', value: 14}, 
        {label: 'Last 30 days', value: 30},
        {label: 'Last 3 months', value: 90},
        {label: 'Last 6 months', value: 180},
        {label: 'Last 1 year', value: 365}
      ], 
      width: "w-auto" 
    }
  ];

  return <FilterBar filters={filters} />;
}
