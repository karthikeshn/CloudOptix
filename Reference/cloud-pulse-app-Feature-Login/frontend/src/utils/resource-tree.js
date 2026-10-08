export function buildResourceMap(filteredResources) {
  const resourceMap = new Map();
  filteredResources.forEach(r => {
    resourceMap.set(r.resource_id, { ...r, children: [] });
  });

  const roots = [];
  resourceMap.forEach(r => {
    let resolvedParentId = r.parent_resource_id;

    // Dynamically link ASGs to their parent ECS Service
    if (r.service_type?.toUpperCase() === 'ASG') {
      const asgName = r.resource_name || r.name || r.resource_id;
      const parentEcs = filteredResources.find(p => p.service_type?.toUpperCase() === 'ECS' && 
        (p.instance_spec?.includes(`ASG: ${r.resource_id}`) || p.instance_spec?.includes(`ASG: ${asgName}`))
      );
      if (parentEcs) {
        resolvedParentId = parentEcs.resource_id;
      }
    }

    // If the parent is missing (e.g. ASG not tagged/discovered), see if an ECS Service claims it
    if (resolvedParentId && !resourceMap.has(resolvedParentId)) {
      const parentEcs = filteredResources.find(p => p.service_type?.toUpperCase() === 'ECS' && p.instance_spec?.includes(`ASG: ${resolvedParentId}`));
      if (parentEcs) {
        resolvedParentId = parentEcs.resource_id;
      }
    }

    if (resolvedParentId && resourceMap.has(resolvedParentId)) {
      resourceMap.get(resolvedParentId).children.push(resourceMap.get(r.resource_id));
    } else {
      roots.push(resourceMap.get(r.resource_id));
    }
  });
  
  // Dynamically calculate aggregated status for root clusters/applications
  const calculateAggregatedStatus = (node) => {
    if (!node.children || node.children.length === 0) return node.status;
    
    const getDescendantStatuses = (n) => {
      let statuses = n.children.map(c => c.status);
      n.children.forEach(c => {
        statuses = statuses.concat(getDescendantStatuses(c));
      });
      return statuses;
    };
    
    const allStatuses = getDescendantStatuses(node).map(s => (s || '').toUpperCase());
    const powerStates = allStatuses.filter(s => ['RUNNING', 'STOPPED', 'STARTING', 'STOPPING'].includes(s));
    
    if (powerStates.length === 0) return node.status;
    
    if (powerStates.some(s => s === 'STARTING')) return 'STARTING';
    if (powerStates.some(s => s === 'STOPPING')) return 'STOPPING';
    
    const allStopped = powerStates.every(s => s === 'STOPPED');
    if (allStopped) return 'STOPPED';
    
    const allRunning = powerStates.every(s => s === 'RUNNING');
    if (allRunning) return 'RUNNING';
    
    return 'PARTIAL';
  };

  roots.forEach(root => {
    if (['ECS', 'EKS', 'BEANSTALK'].includes((root.service_type || '').toUpperCase())) {
      root.status = calculateAggregatedStatus(root);
    }
  });

  return { resourceMap, roots };
}

export function buildResourceTree(filteredResources, isGroupView, expandedRowIds) {
  if (!isGroupView) {
    return filteredResources.map(r => ({ ...r, _level: 0, _isExpandable: false }));
  }

  const { roots } = buildResourceMap(filteredResources);

  // 3. Flatten the tree based on expandedRowIds
  const flattenTree = (nodes, level = 0) => {
    let result = [];
    for (const node of nodes) {
      const isExpandable = node.children.length > 0;
      const isExpanded = expandedRowIds.has(node.resource_id);
      result.push({ ...node, _level: level, _isExpandable: isExpandable, _isExpanded: isExpanded });
      
      if (isExpanded && isExpandable) {
        result = result.concat(flattenTree(node.children, level + 1));
      }
    }
    return result;
  };

  return flattenTree(roots);
}
