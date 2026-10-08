export const CloudStrategies = {
  aws: {
    getLinkedAccount: (nativeId) => {
      if (!nativeId) return 'Unknown';
      const parts = nativeId.split(':');
      if (parts.length > 4 && parts[4]) return parts[4];
      return 'Unknown';
    },
    getResourceGroup: (resourceType) => {
      if (!resourceType) return 'UNKNOWN';
      return resourceType.split(':')[0].toUpperCase();
    },
    formatType: (rawType, nativeId) => {
      if (!rawType || rawType === 'Unknown') {
        if (nativeId && nativeId.startsWith('arn:aws:')) {
          const parts = nativeId.split(':');
          if (parts.length >= 6) {
            const service = parts[2].toUpperCase();
            const resourcePart = parts[5];
            if (resourcePart && resourcePart.includes('/')) {
              const rType = resourcePart.split('/')[0];
              return `${service} ${rType.charAt(0).toUpperCase() + rType.slice(1)}`;
            }
            return `${service} Resource`;
          }
        }
        return 'Unknown';
      }
      if (rawType.includes('::')) return rawType.split('::').pop();
      const parts = rawType.split(':');
      if (parts.length > 1) {
        const service = parts[0].toUpperCase();
        const resource = parts[1].charAt(0).toUpperCase() + parts[1].slice(1).replace(/-/g, ' ');
        return `${service} ${resource}`;
      }
      return rawType;
    },
    formatIdentifier: (nativeId) => {
      if (!nativeId) return 'Unknown';
      if (nativeId.includes('/')) return nativeId.split('/').pop();
      return nativeId.split(':').pop();
    },
    formatName: (name, nativeId) => {
      return name; // AWS keeps raw name
    }
  },
  azure: {
    getLinkedAccount: (nativeId) => {
      if (!nativeId) return 'Unknown';
      // format: /subscriptions/<sub_id>/resourceGroups/...
      const parts = nativeId.split('/');
      if (parts.length > 2 && parts[1].toLowerCase() === 'subscriptions') {
        return parts[2];
      }
      return 'Unknown';
    },
    getResourceGroup: (resourceType, nativeId) => {
      if (!resourceType) return 'UNKNOWN';
      const parts = resourceType.split('/');
      if (parts.length > 0) {
        return parts[0].replace(/microsoft\./i, '').toUpperCase();
      }
      return 'UNKNOWN';
    },
    formatType: (rawType) => {
      if (!rawType) return 'Unknown';
      // format: microsoft.compute/virtualmachines
      const parts = rawType.split('/');
      if (parts.length > 1) {
        const resource = parts[1].replace(/([A-Z])/g, ' $1').trim(); // simple camel case split
        return resource.charAt(0).toUpperCase() + resource.slice(1);
      }
      return rawType;
    },
    formatIdentifier: (nativeId) => {
      if (!nativeId) return 'Unknown';
      return nativeId.split('/').pop();
    },
    formatName: (name, nativeId) => {
      return name; // Azure keeps raw name
    }
  },
  gcp: {
    getLinkedAccount: (nativeId) => {
      if (!nativeId) return 'Unknown';
      const projectMatch = nativeId.match(/\/projects\/([^/]+)/);
      if (projectMatch && projectMatch[1]) return projectMatch[1];
      return 'Unknown';
    },
    getResourceGroup: (resourceType) => {
      if (!resourceType) return 'UNKNOWN';
      return resourceType.split('.')[0].toUpperCase();
    },
    formatType: (rawType) => {
      if (!rawType) return 'Unknown';
      const parts = rawType.split('/');
      if (parts.length > 1) {
        return parts.pop();
      }
      return rawType;
    },
    formatIdentifier: (nativeId) => {
      if (!nativeId) return 'Unknown';
      
      let friendlyName = nativeId.split('/').pop();
      
      if (friendlyName.length >= 30) {
        return `${friendlyName.substring(0, 15)}...${friendlyName.slice(-8)}`;
      }
      
      return friendlyName;
    },
    formatName: (name, nativeId) => {
      // If the backend gave us a very long UUID or hash as the name, let's nicely truncate it.
      if (name && name.length >= 30) {
        return `${name.substring(0, 15)}...${name.slice(-8)}`;
      }
      return name;
    }
  }
};

export function getStrategy(providerStr) {
  const provider = (providerStr || 'aws').toLowerCase();
  return CloudStrategies[provider] || CloudStrategies.aws;
}
