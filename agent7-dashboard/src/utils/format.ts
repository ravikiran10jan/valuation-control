export function formatCurrency(value: number, compact = false): string {
  const formatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: compact ? 1 : 0,
    notation: compact ? 'compact' : 'standard',
  });
  return formatter.format(value);
}

export function formatNumber(value: number, decimals = 0): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatPercent(value: number, decimals = 1): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`;
}

export function formatDate(date: string | Date | undefined | null): string {
  if (!date) return '-';
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return '-';
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatDateTime(date: string | Date | undefined | null): string {
  if (!date) return '-';
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return '-';
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function formatRelativeTime(date: string | Date | undefined | null): string {
  if (!date) return '-';
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return '-';
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hours ago`;
  if (diffDays < 7) return `${diffDays} days ago`;
  return formatDate(d);
}

export function getSeverityColor(severity: string): string {
  switch (severity.toUpperCase()) {
    case 'RED':
    case 'HIGH':
    case 'CRITICAL':
      return 'text-red-400';
    case 'AMBER':
    case 'MEDIUM':
    case 'WARNING':
      return 'text-amber-400';
    case 'GREEN':
    case 'LOW':
    case 'OK':
      return 'text-green-400';
    default:
      return 'text-gray-400';
  }
}

export function getSeverityBgColor(severity: string): string {
  switch (severity.toUpperCase()) {
    case 'RED':
    case 'HIGH':
    case 'CRITICAL':
      return 'bg-red-500/20 text-red-400';
    case 'AMBER':
    case 'MEDIUM':
    case 'WARNING':
      return 'bg-amber-500/20 text-amber-400';
    case 'GREEN':
    case 'LOW':
    case 'OK':
      return 'bg-green-500/20 text-green-400';
    default:
      return 'bg-gray-500/20 text-gray-400';
  }
}

export function getStatusColor(status: string): string {
  switch (status.toUpperCase()) {
    case 'COMPLETED':
    case 'RESOLVED':
      return 'text-green-400';
    case 'IN_PROGRESS':
    case 'INVESTIGATING':
      return 'text-blue-400';
    case 'PENDING':
    case 'OPEN':
      return 'text-amber-400';
    case 'FAILED':
    case 'ESCALATED':
      return 'text-red-400';
    default:
      return 'text-gray-400';
  }
}

export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}
