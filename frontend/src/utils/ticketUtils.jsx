import React from 'react';
import { 
  FaAws, FaDatabase, FaHdd, FaNetworkWired, FaShieldAlt, FaServer,
  FaFolderOpen, FaFolder, FaCopy, FaSave, FaTable, FaGlobe, FaSlidersH, 
  FaRoute, FaCubes, FaBolt, FaCodeBranch, FaLayerGroup, FaTachometerAlt, 
  FaPuzzlePiece, FaUserShield, FaStream, FaEye, FaArchive, FaSearch, FaCube, FaMemory
} from 'react-icons/fa';

export const SCRIPT_CATEGORIES = {
  "Storage & Volumes": ["EBS", "Efs", "S3", "ECR", "Bucket", "Disk", "gp2", "gp3", "AWS"],
  "Snapshots & Backups": ["Snapshot", "Backup", "AMI", "RecoveryPoint", "AWS"],
  "Databases & Cache": ["RDS", "DynamoDB", "Elastic Cache", "Valkey", "ElasticSearch", "Database", "AWS"],
  "Networking & IP": ["IPV4", "IPV6", "Vpc", "Cloudfront", "Data Transfer", "Global Accelerator", "Egress", "Load Balancer", "AWS"],
  "Compute & Management": ["EC2", "EKS", "Eks", "Lambda", "CodePipeline", "Codepipeline", "Compute Optimizer", "CloudFormation", "Access Analyzer", "AWS"],
  "Analytics & Security": ["Glue", "Guardduty", "Kinesis", "Cloudwatch", "AWS"],
  "Internal Utilities": ["Internal", "AWS"],
  "Other": ["AWS"]
};

import scriptManifest from './scriptManifest.json';

export const getScriptCategory = (scriptName) => {
  // 1. Hardcoded manifest lookup (Primary Source of Truth)
  if (scriptManifest[scriptName] && scriptManifest[scriptName].category) {
    return scriptManifest[scriptName].category;
  }
  
  // 2. Legacy fallback
  const name = scriptName.toLowerCase();
  for (const [category, keywords] of Object.entries(SCRIPT_CATEGORIES)) {
    if (keywords.some(kw => name.includes(kw.toLowerCase()))) {
      return category;
    }
  }
  if (name.includes('fix_') || name.includes('test_') || name.includes('refactor_')) {
    return "Internal Utilities";
  }
  return "Other";
};

export const getCategoryTheme = (category) => {
  switch (category) {
    case "Storage & Volumes": return { color: '#569E3D', bg: 'rgba(86, 158, 61, 0.15)' };
    case "Snapshots & Backups": return { color: '#818cf8', bg: 'rgba(129, 140, 248, 0.15)' };
    case "Databases & Cache": return { color: '#527FFF', bg: 'rgba(82, 127, 255, 0.15)' };
    case "Networking & IP": return { color: '#FF9900', bg: 'rgba(255, 153, 0, 0.15)' };
    case "Compute & Management": return { color: '#EC7211', bg: 'rgba(236, 114, 17, 0.15)' };
    case "Analytics & Security": return { color: '#f472b6', bg: 'rgba(244, 114, 182, 0.15)' };
    default: return { color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.15)' };
  }
};

export const renderAwsIcon = (scriptName, category) => {
  const name = scriptName.toLowerCase();
  const iconSize = 22;

  if (name.includes('s3') || name.includes('bucket')) return <FaFolderOpen color="#569E3D" size={iconSize} />;
  if (name.includes('ebs') || name.includes('disk') || name.includes('gp2') || name.includes('gp3')) return <FaHdd color="#569E3D" size={iconSize} />;
  if (name.includes('efs')) return <FaFolder color="#569E3D" size={iconSize} />;
  if (name.includes('ecr')) return <FaCube color="#EC7211" size={iconSize} />;
  if (name.includes('archive')) return <FaArchive color="#569E3D" size={iconSize} />;
  if (name.includes('ami') || name.includes('snapshot')) return <FaCopy color="#818cf8" size={iconSize} />;
  if (name.includes('backup')) return <FaSave color="#818cf8" size={iconSize} />;
  if (name.includes('dynamodb')) return <FaTable color="#405BF8" size={iconSize} />;
  if (name.includes('rds') || name.includes('database')) return <FaDatabase color="#527FFF" size={iconSize} />;
  if (name.includes('elastic cache') || name.includes('valkey')) return <FaMemory color="#527FFF" size={iconSize} />;
  if (name.includes('elasticsearch')) return <FaSearch color="#527FFF" size={iconSize} />;
  if (name.includes('cloudfront')) return <FaGlobe color="#FF9900" size={iconSize} />;
  if (name.includes('load balancer') || name.includes('elb')) return <FaSlidersH color="#FF9900" size={iconSize} />;
  if (name.includes('global accelerator')) return <FaRoute color="#FF9900" size={iconSize} />;
  if (name.includes('vpc') || name.includes('ipv4') || name.includes('ipv6') || name.includes('egress') || name.includes('data transfer')) return <FaNetworkWired color="#FF9900" size={iconSize} />;
  if (name.includes('eks')) return <FaCubes color="#FF9900" size={iconSize} />;
  if (name.includes('ec2')) return <FaServer color="#FF9900" size={iconSize} />;
  if (name.includes('lambda')) return <FaBolt color="#EC7211" size={iconSize} />;
  if (name.includes('codepipeline') || name.includes('pipeline')) return <FaCodeBranch color="#EC7211" size={iconSize} />;
  if (name.includes('cloudformation')) return <FaLayerGroup color="#EC7211" size={iconSize} />;
  if (name.includes('compute optimizer')) return <FaTachometerAlt color="#EC7211" size={iconSize} />;
  if (name.includes('glue')) return <FaPuzzlePiece color="#f472b6" size={iconSize} />;
  if (name.includes('guardduty')) return <FaShieldAlt color="#f472b6" size={iconSize} />;
  if (name.includes('access analyzer')) return <FaUserShield color="#f472b6" size={iconSize} />;
  if (name.includes('kinesis')) return <FaStream color="#f472b6" size={iconSize} />;
  if (name.includes('cloudwatch')) return <FaEye color="#818cf8" size={iconSize} />;

  if (category === "Storage & Volumes") return <FaFolderOpen color="#569E3D" size={iconSize} />;
  if (category === "Snapshots & Backups") return <FaCopy color="#818cf8" size={iconSize} />;
  if (category === "Databases & Cache") return <FaDatabase color="#527FFF" size={iconSize} />;
  if (category === "Networking & IP") return <FaNetworkWired color="#FF9900" size={iconSize} />;
  if (category === "Compute & Management") return <FaServer color="#EC7211" size={iconSize} />;
  if (category === "Analytics & Security") return <FaShieldAlt color="#f472b6" size={iconSize} />;

  return <FaAws color="#FF9900" size={iconSize} />;
};

export const getScriptDescription = (scriptName) => {
  let clean = scriptName.replace('.py', '').trim();
  
  // Add spaces to CamelCase if no spaces exist
  if (!clean.includes(' ') && !clean.includes('_')) {
    clean = clean.replace(/([A-Z])/g, ' $1').trim();
  }
  
  // Clean up underscores or extra spaces
  clean = clean.replace(/_/g, ' ').replace(/\s+/g, ' ');
  
  const lowerClean = clean.toLowerCase();
  
  if (lowerClean.startsWith('delete') || lowerClean.startsWith('remove') || lowerClean.startsWith('stop')) {
    return `Identify and ${lowerClean} to eliminate wasted cloud spend and optimize infrastructure.`;
  }
  
  if (lowerClean.includes('idle') || lowerClean.includes('unused') || lowerClean.includes('unattached') || lowerClean.includes('empty')) {
    return `Detect ${lowerClean} to reclaim resources and reduce unnecessary monthly costs.`;
  }
  
  if (lowerClean.includes('missing') || lowerClean.includes('without')) {
    return `Highlight resources ${lowerClean} to improve compliance, security, and cost efficiency.`;
  }
  
  return `Analyze AWS accounts for ${lowerClean} opportunities to ensure cost optimization and best practices.`;
};
