import { getStrategy } from './cloud-strategies';

export function formatType(rawType, provider = 'aws', nativeId = null) {
  return getStrategy(provider).formatType(rawType, nativeId);
}

export function formatIdentifier(nativeId, provider = 'aws') {
  return getStrategy(provider).formatIdentifier(nativeId);
}

export function formatName(name, nativeId, provider = 'aws') {
  const strategy = getStrategy(provider);
  if (strategy.formatName) return strategy.formatName(name, nativeId);
  return name;
}

export function getTodayPrefix() {
  const d = new Date();
  d.setMinutes(d.getMinutes() + d.getTimezoneOffset() + 330);
  return d.toISOString().split('T')[0];
}
