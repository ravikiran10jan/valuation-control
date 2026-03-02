import { useState, useEffect } from 'react';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Search,
  Grid3X3,
  Star,
} from 'lucide-react';
import { cn } from '@/utils/format';

// ── Types ───────────────────────────────────────────────────

interface ApplicabilityEntry {
  product: string;
  asset_class: string;
  applicable_models: {
    model_id: string;
    model_name: string;
    rating: 'preferred' | 'valid' | 'limited' | 'invalid';
    notes: string;
  }[];
}

interface RecommendationEntry {
  model_id: string;
  model_name: string;
  rating: string;
  notes: string;
  product: string;
  asset_class: string;
}

// ── API helpers ─────────────────────────────────────────────

const API = '/api/simulator';

async function fetchApplicabilityMatrix(): Promise<ApplicabilityEntry[]> {
  const res = await fetch(`${API}/applicability`);
  if (!res.ok) throw new Error('Failed to fetch applicability matrix');
  return res.json();
}

async function fetchRecommendations(
  product: string,
): Promise<RecommendationEntry[]> {
  const res = await fetch(
    `${API}/applicability/recommend?product=${encodeURIComponent(product)}`,
  );
  if (!res.ok) throw new Error('Failed to fetch recommendations');
  return res.json();
}

// ── Rating config ───────────────────────────────────────────

const RATING_CONFIG: Record<
  string,
  { label: string; icon: typeof CheckCircle2; color: string; bg: string; border: string }
> = {
  preferred: {
    label: 'Preferred',
    icon: Star,
    color: 'text-green-700',
    bg: 'bg-green-50',
    border: 'border-green-200',
  },
  valid: {
    label: 'Valid',
    icon: CheckCircle2,
    color: 'text-blue-700',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
  },
  limited: {
    label: 'Limited',
    icon: AlertTriangle,
    color: 'text-amber-700',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
  },
  invalid: {
    label: 'Invalid',
    icon: XCircle,
    color: 'text-red-700',
    bg: 'bg-red-50',
    border: 'border-red-200',
  },
};

const ASSET_CLASS_COLORS: Record<string, string> = {
  equity: 'bg-blue-100 text-blue-700 border-blue-200',
  rates: 'bg-violet-100 text-violet-700 border-violet-200',
  credit: 'bg-orange-100 text-orange-700 border-orange-200',
  fx: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  commodity: 'bg-amber-100 text-amber-700 border-amber-200',
  income: 'bg-teal-100 text-teal-700 border-teal-200',
};

// ── Component ───────────────────────────────────────────────

export function ApplicabilityPage() {
  const [matrix, setMatrix] = useState<ApplicabilityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [recommendations, setRecommendations] = useState<
    RecommendationEntry[] | null
  >(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [filterRating, setFilterRating] = useState<string>('all');

  useEffect(() => {
    fetchApplicabilityMatrix()
      .then((data) => {
        setMatrix(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    setRecommendations(null);
    try {
      const recs = await fetchRecommendations(searchQuery.trim());
      setRecommendations(recs);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setSearchLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-enterprise-500">Loading applicability matrix...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
        <div className="flex items-center gap-3 mb-3">
          <Grid3X3 size={20} className="text-primary-600" />
          <h2 className="text-lg font-bold text-enterprise-900">
            Product × Model Applicability Matrix
          </h2>
        </div>
        <p className="text-sm text-enterprise-500">
          This matrix shows which pricing models are applicable for each product
          type, along with their suitability rating. Use this to select the
          right model for your instrument.
        </p>
      </div>

      {/* Search */}
      <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
        <h3 className="text-sm font-semibold text-enterprise-800 mb-3">
          Find Models for a Product
        </h3>
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-enterprise-400"
            />
            <input
              type="text"
              placeholder="e.g., European equity option, CDS, swaption..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="w-full pl-9 pr-3 py-2 border border-enterprise-200 rounded-lg text-sm"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={searchLoading || !searchQuery.trim()}
            className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
          >
            {searchLoading ? 'Searching...' : 'Search'}
          </button>
        </div>

        {/* Recommendations */}
        {recommendations && (
          <div className="mt-4">
            {recommendations.length === 0 ? (
              <p className="text-sm text-enterprise-500">
                No matching models found. Try a different product description.
              </p>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-enterprise-400 font-medium uppercase tracking-wider">
                  {recommendations.length} matching model
                  {recommendations.length !== 1 ? 's' : ''}
                </p>
                {recommendations.map((rec) => {
                  const ratingCfg = RATING_CONFIG[rec.rating] || RATING_CONFIG.valid;
                  const RatingIcon = ratingCfg.icon;
                  return (
                    <div
                      key={rec.model_id}
                      className={cn(
                        'flex items-center justify-between p-3 rounded-lg border',
                        ratingCfg.bg,
                        ratingCfg.border,
                      )}
                    >
                      <div className="flex items-center gap-3">
                        <RatingIcon size={16} className={ratingCfg.color} />
                        <div>
                          <div className="text-sm font-medium text-enterprise-800">
                            {rec.model_name}
                          </div>
                          <div className="text-xs text-enterprise-500">
                            {rec.notes}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            'px-2 py-0.5 rounded text-[10px] font-semibold uppercase border',
                            ASSET_CLASS_COLORS[rec.asset_class] ||
                              'bg-enterprise-50 text-enterprise-600 border-enterprise-200',
                          )}
                        >
                          {rec.asset_class}
                        </span>
                        <span
                          className={cn(
                            'px-2 py-0.5 rounded text-[10px] font-semibold uppercase',
                            ratingCfg.color,
                          )}
                        >
                          {ratingCfg.label}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-enterprise-500">Filter:</span>
        {['all', 'preferred', 'valid', 'limited'].map((r) => (
          <button
            key={r}
            onClick={() => setFilterRating(r)}
            className={cn(
              'px-3 py-1 rounded-full text-xs font-medium transition-colors border',
              filterRating === r
                ? 'bg-primary-100 text-primary-700 border-primary-200'
                : 'bg-white text-enterprise-500 border-enterprise-200 hover:bg-enterprise-50',
            )}
          >
            {r === 'all' ? 'All Ratings' : r.charAt(0).toUpperCase() + r.slice(1)}
          </button>
        ))}
      </div>

      {/* Matrix Cards */}
      <div className="space-y-4">
        {matrix.map((entry) => {
          const models =
            filterRating === 'all'
              ? entry.applicable_models
              : entry.applicable_models.filter((m) => m.rating === filterRating);

          if (models.length === 0) return null;

          return (
            <div
              key={entry.product}
              className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5"
            >
              <div className="flex items-center gap-3 mb-3">
                <span
                  className={cn(
                    'px-2 py-0.5 rounded text-[10px] font-semibold uppercase border',
                    ASSET_CLASS_COLORS[entry.asset_class] ||
                      'bg-enterprise-50 text-enterprise-600 border-enterprise-200',
                  )}
                >
                  {entry.asset_class}
                </span>
                <h3 className="text-sm font-semibold text-enterprise-800">
                  {entry.product}
                </h3>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {models.map((m) => {
                  const ratingCfg =
                    RATING_CONFIG[m.rating] || RATING_CONFIG.valid;
                  const RatingIcon = ratingCfg.icon;
                  return (
                    <div
                      key={m.model_id}
                      className={cn(
                        'flex items-start gap-2.5 p-3 rounded-lg border',
                        ratingCfg.bg,
                        ratingCfg.border,
                      )}
                    >
                      <RatingIcon
                        size={14}
                        className={cn(ratingCfg.color, 'mt-0.5 flex-shrink-0')}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-enterprise-800">
                            {m.model_name}
                          </span>
                          <span
                            className={cn(
                              'text-[10px] font-semibold uppercase',
                              ratingCfg.color,
                            )}
                          >
                            {ratingCfg.label}
                          </span>
                        </div>
                        <p className="text-xs text-enterprise-500 mt-0.5">
                          {m.notes}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-4">
        <h4 className="text-xs font-semibold text-enterprise-500 uppercase tracking-wider mb-2">
          Rating Legend
        </h4>
        <div className="flex flex-wrap gap-4">
          {Object.entries(RATING_CONFIG).map(([key, cfg]) => {
            const Icon = cfg.icon;
            return (
              <div key={key} className="flex items-center gap-1.5 text-xs">
                <Icon size={12} className={cfg.color} />
                <span className={cn('font-medium', cfg.color)}>
                  {cfg.label}
                </span>
                <span className="text-enterprise-400">
                  {key === 'preferred'
                    ? '- Industry standard'
                    : key === 'valid'
                      ? '- Acceptable alternative'
                      : key === 'limited'
                        ? '- Use with caution'
                        : '- Not recommended'}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
