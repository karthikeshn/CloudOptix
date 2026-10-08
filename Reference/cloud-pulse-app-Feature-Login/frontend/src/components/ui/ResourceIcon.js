import React from 'react';
import { Server, Database, Box, Network, Layers, Copy, Cpu, Monitor, Rocket, Cloud } from 'lucide-react';

const ICON_MAP = {
  // Compute
  EC2: Server,
  VM: Server,
  COMPUTE: Server,
  
  // Database / Data
  RDS: Database,
  AURORA: Database,
  DOCUMENTDB: Database,
  REDSHIFT: Database,
  SQL: Database,
  CLOUDSQL: Database,

  // Containers & Kubernetes
  EKS: Network,
  AKS: Network,
  GKE: Network,
  ECS: Box,

  // App & Scaling Platforms
  BEANSTALK: Layers,
  ASG: Copy,
  APPRUNNER: Rocket,

  // AI & ML
  SAGEMAKER: Cpu,

  // End User Computing
  WORKSPACES: Monitor,
};

export function ResourceIcon({ serviceType, className = "w-3.5 h-3.5" }) {
  const type = (serviceType || '').toUpperCase();
  
  // Dynamically resolve the icon component, falling back to Cloud
  const IconComponent = ICON_MAP[type] || Cloud;
  
  return <IconComponent className={className} />;
}
