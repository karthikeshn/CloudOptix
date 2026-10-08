import { useState, useEffect } from 'react';
import { getStrategy } from '../utils/cloud-strategies';

/**
 * Custom hook to manage complex cascading filter logic across Control and Inventory modules.
 * Rules:
 * 1. Region changes -> Update Group and Type counts.
 * 2. Group changes -> Update Region and Type counts.
 * 3. Type changes -> Update Region counts, but DO NOT update Group counts.
 */
export function useDynamicFilters({
  module, // 'inventory' or 'control'
  fetchSummary, // The API function to call
  filters, // The local filters (group, type, region, etc.)
  topFilters, // The global top-level filters (account, provider, tag, etc.)
  dynamicGroups, // Global fallback options
  dynamicTypes,
  dynamicRegions,
  getGroupFn, // Optional custom grouping function
  activeTypeParam // The computed type parameter for the active filter
}) {
  const [dropdownOptions, setDropdownOptions] = useState({
    groupOptions: [],
    typeOptions: [],
    regionOptions: []
  });

  const dynGroupsLen = (dynamicGroups || []).length;
  const dynTypesLen = (dynamicTypes || []).length;
  const dynRegionsLen = (dynamicRegions || []).length;

  useEffect(() => {
    let isMounted = true;
    const strategy = getStrategy(topFilters.provider || 'aws');

    const loadOptions = async () => {
      try {
        const getGroup = getGroupFn || ((type, nativeId) => strategy.getResourceGroup(type, nativeId));
        
        let groupSummaryPromise;
        let activeSummaryPromise;

        if (module === 'inventory') {
          groupSummaryPromise = fetchSummary(
            topFilters.account, topFilters.provider, 
            filters.region === 'All' ? null : filters.region, 
            topFilters.linked, topFilters.tag, null // No type filter
          );
          
          activeSummaryPromise = fetchSummary(
            topFilters.account, topFilters.provider, 
            filters.region === 'All' ? null : filters.region, 
            topFilters.linked, topFilters.tag, 
            activeTypeParam
          );
        } else if (module === 'control') {
          groupSummaryPromise = fetchSummary({
            account: topFilters.account,
            provider: topFilters.provider,
            region: filters.region === 'All' ? topFilters.region : filters.region,
            tag: topFilters.tag,
            status: filters.powerState === 'All' ? null : filters.powerState,
            serviceType: null // No type filter
          });

          activeSummaryPromise = fetchSummary({
            account: topFilters.account,
            provider: topFilters.provider,
            region: filters.region === 'All' ? topFilters.region : filters.region,
            tag: topFilters.tag,
            status: filters.powerState === 'All' ? null : filters.powerState,
            serviceType: activeTypeParam
          });
        }

        const [groupRes, activeRes] = await Promise.all([groupSummaryPromise, activeSummaryPromise]);
        
        if (!isMounted) return;

        const groupTypeBreakdown = module === 'inventory' ? 
          (filters.isDeletedTab ? groupRes.data?.deleted_type_breakdown : groupRes.data?.type_breakdown) || [] : 
          groupRes.type_breakdown || [];
          
        const activeTypeBreakdown = module === 'inventory' ? 
          (filters.isDeletedTab ? activeRes.data?.deleted_type_breakdown : activeRes.data?.type_breakdown) || [] : 
          activeRes.type_breakdown || [];
          
        const activeRegionBreakdown = module === 'inventory' ? 
          (filters.isDeletedTab ? activeRes.data?.deleted_region_breakdown : activeRes.data?.region_breakdown) || [] : 
          activeRes.region_breakdown || [];

        let baseGroups = dynamicGroups || [];
        if (baseGroups.length === 0) {
          const groupSet = new Set();
          groupTypeBreakdown.forEach(t => {
            const g = getGroup(t.type, '');
            if (!groupSet.has(g)) {
              groupSet.add(g);
              baseGroups.push({ group: g, label: g.toUpperCase(), count: 0 });
            }
          });
        }

        const currentGroupOptions = baseGroups.map(dg => {
          let count = 0;
          groupTypeBreakdown.forEach(t => {
            const g = getGroup(t.type, '');
            if (g === (dg.group || dg.value)) count += t.count;
          });
          return { group: dg.group || dg.value, label: dg.label, count: count };
        }).filter(g => g.count > 0 || g.group === filters.group);

        let baseTypesArr = dynamicTypes || [];
        if (baseTypesArr.length === 0) {
           groupTypeBreakdown.forEach(t => {
             baseTypesArr.push({ type: t.type, label: t.type, count: 0 });
           });
        }
        
        const baseTypes = filters.group === 'All' ? baseTypesArr : baseTypesArr.filter(t => getGroup(t.type || t.value, '') === (filters.group || filters.groupValue));
        
        const currentTypeOptions = baseTypes.map(dt => {
          const typeVal = dt.type || dt.value;
          const match = activeTypeBreakdown.find(t => t.type === typeVal);
          const count = match ? match.count : 0;
          
          const displayCount = count === 0 && filters.type !== 'All' && filters.type !== typeVal ? (dt.count || 0) : count;
          return { type: typeVal, label: dt.label, count: displayCount };
        }).filter(t => t.count > 0 || t.type === filters.type);

        let baseRegionsArr = dynamicRegions || [];
        const currentRegionOptions = baseRegionsArr.map(dr => {
          const regionVal = dr.region || dr.value;
          const match = activeRegionBreakdown.find(r => r.region === regionVal);
          const count = match ? match.count : 0;
          
          const displayCount = count === 0 && filters.region !== 'All' && filters.region !== regionVal ? (dr.count || 0) : count;
          return { region: regionVal, label: dr.label, count: displayCount };
        }).filter(r => r.count > 0 || r.region === filters.region);

        setDropdownOptions({
          groupOptions: currentGroupOptions,
          typeOptions: currentTypeOptions,
          regionOptions: currentRegionOptions
        });

      } catch (err) {
        console.error(`Failed to load dynamic filters for ${module}`, err);
      }
    };

    if ((dynamicGroups || []).length > 0 || module === 'control') {
      loadOptions();
    }

    return () => {
      isMounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    module,
    filters.group, filters.type, filters.region, filters.powerState, filters.isDeletedTab,
    topFilters.account, topFilters.provider, topFilters.region, topFilters.tag, topFilters.linked,
    dynGroupsLen, dynTypesLen, dynRegionsLen, activeTypeParam
  ]);

  return dropdownOptions;
}
