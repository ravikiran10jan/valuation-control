import type { ReactNode } from 'react';
import { cn } from '@/utils/format';

interface CardProps {
  title?: ReactNode;
  children: ReactNode;
  className?: string;
  headerAction?: ReactNode;
}

export function Card({ title, children, className, headerAction }: CardProps) {
  return (
    <div
      className={cn(
        'bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card',
        className
      )}
    >
      {title && (
        <div className="flex items-center justify-between px-6 py-4 border-b border-enterprise-100">
          <h3 className="text-base font-semibold text-enterprise-800">{title}</h3>
          {headerAction}
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  );
}

interface KPICardProps {
  title: string;
  value: string | number;
  trend?: string;
  trendDirection?: 'up' | 'down' | 'neutral';
  color?: 'default' | 'red' | 'amber' | 'green';
  icon?: ReactNode;
}

export function KPICard({
  title,
  value,
  trend,
  trendDirection = 'neutral',
  color = 'default',
  icon,
}: KPICardProps) {
  const colorClasses = {
    default: 'border-enterprise-200 bg-white',
    red: 'border-red-200 bg-red-50',
    amber: 'border-amber-200 bg-amber-50',
    green: 'border-green-200 bg-green-50',
  };

  const trendColors = {
    up: 'text-green-600',
    down: 'text-red-600',
    neutral: 'text-enterprise-500',
  };

  const trendBgColors = {
    up: 'bg-green-100',
    down: 'bg-red-100',
    neutral: 'bg-enterprise-100',
  };

  return (
    <div
      className={cn(
        'rounded-xl border p-5 shadow-enterprise-card transition-shadow hover:shadow-enterprise-md',
        colorClasses[color]
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-enterprise-500 mb-1 truncate">{title}</p>
          <p className="text-2xl font-bold text-enterprise-900">{value}</p>
          {trend && (
            <div className="mt-2">
              <span className={cn(
                'inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full',
                trendBgColors[trendDirection],
                trendColors[trendDirection]
              )}>
                {trend}
              </span>
            </div>
          )}
        </div>
        {icon && (
          <div className={cn(
            'p-2.5 rounded-lg',
            color === 'default' ? 'bg-enterprise-100' : 
            color === 'red' ? 'bg-red-100' :
            color === 'amber' ? 'bg-amber-100' : 'bg-green-100'
          )}>
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
