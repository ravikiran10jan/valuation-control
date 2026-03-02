import { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  ChevronRight,
  ChevronDown,
  Play,
  FlaskConical,
  GitCompare,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
  Calculator,
  BookOpen,
  Beaker,
  BarChart3,
} from 'lucide-react';
import { cn } from '@/utils/format';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';

// ── Types ───────────────────────────────────────────────────

interface ParameterSpec {
  name: string;
  label: string;
  description: string;
  type: string;
  default: number | string;
  min_value: number | null;
  max_value: number | null;
  step: number | null;
  options: string[] | null;
  unit: string;
}

interface ModelMetadata {
  model_id: string;
  model_name: string;
  product_type: string;
  asset_class: string;
  short_description: string;
  long_description: string;
  when_to_use: string[];
  when_not_to_use: string[];
  assumptions: string[];
  limitations: string[];
  formula_latex: string;
  formula_plain: string;
  parameters: ParameterSpec[];
  samples: Record<string, Record<string, number | string>>;
}

interface CalculationStep {
  step_number: number;
  label: string;
  formula: string;
  substitution: string;
  result: number;
  explanation: string;
}

interface CalcResult {
  model_id: string;
  model_name: string;
  fair_value: number;
  method: string;
  greeks: Record<string, number>;
  calculation_steps: CalculationStep[];
  diagnostics: Record<string, unknown>;
}

interface ProductEntry {
  model_id: string;
  model_name: string;
  product_type: string;
  short_description: string;
}

type ProductMap = Record<string, ProductEntry[]>;

// ── API helpers ─────────────────────────────────────────────

const API = '/api/simulator';

async function fetchProducts(): Promise<ProductMap> {
  const res = await fetch(`${API}/products`);
  if (!res.ok) throw new Error('Failed to fetch products');
  return res.json();
}

async function fetchModelMeta(modelId: string): Promise<ModelMetadata> {
  const res = await fetch(`${API}/models/${modelId}`);
  if (!res.ok) throw new Error(`Failed to fetch model ${modelId}`);
  return res.json();
}

async function runCalculation(
  modelId: string,
  parameters: Record<string, unknown>,
): Promise<CalcResult> {
  const res = await fetch(`${API}/calculate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, parameters }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Calculation failed');
  }
  return res.json();
}

async function runComparison(
  modelIds: string[],
  parameters: Record<string, unknown>,
): Promise<{ results: CalcResult[]; comparison: Record<string, unknown> }> {
  const res = await fetch(`${API}/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_ids: modelIds, parameters }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Comparison failed');
  }
  return res.json();
}

interface SensitivityResult {
  sweep_param: string;
  sweep_values: number[];
  models: Record<
    string,
    {
      model_name: string;
      prices: (number | null)[];
      deltas: (number | null)[];
    }
  >;
  model_reserve: number[];
}

async function runSensitivity(
  modelIds: string[],
  parameters: Record<string, unknown>,
  sweepParam: string,
  sweepMin: number,
  sweepMax: number,
  sweepSteps: number = 20,
): Promise<SensitivityResult> {
  const res = await fetch(`${API}/sensitivity`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model_ids: modelIds,
      parameters,
      sweep_param: sweepParam,
      sweep_min: sweepMin,
      sweep_max: sweepMax,
      sweep_steps: sweepSteps,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Sensitivity failed');
  }
  return res.json();
}

// ── Asset class display ─────────────────────────────────────

const ASSET_CLASS_CONFIG: Record<
  string,
  { label: string; color: string; bg: string }
> = {
  equity: {
    label: 'Equity',
    color: 'text-blue-700',
    bg: 'bg-blue-50 border-blue-200',
  },
  fx: {
    label: 'FX',
    color: 'text-emerald-700',
    bg: 'bg-emerald-50 border-emerald-200',
  },
  rates: {
    label: 'Rates',
    color: 'text-violet-700',
    bg: 'bg-violet-50 border-violet-200',
  },
  credit: {
    label: 'Credit',
    color: 'text-orange-700',
    bg: 'bg-orange-50 border-orange-200',
  },
  commodity: {
    label: 'Commodity',
    color: 'text-amber-700',
    bg: 'bg-amber-50 border-amber-200',
  },
};

// ── Main component ──────────────────────────────────────────

export function SimulatorPage() {
  // State
  const [products, setProducts] = useState<ProductMap>({});
  const [expandedClasses, setExpandedClasses] = useState<Set<string>>(
    new Set(['equity']),
  );
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [modelMeta, setModelMeta] = useState<ModelMetadata | null>(null);
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [selectedSample, setSelectedSample] = useState<string>('');
  const [result, setResult] = useState<CalcResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const [compareMode, setCompareMode] = useState(false);
  const [compareModelIds, setCompareModelIds] = useState<Set<string>>(
    new Set(),
  );
  const [compareResults, setCompareResults] = useState<{
    results: CalcResult[];
    comparison: Record<string, unknown>;
  } | null>(null);
  const [sensitivityResult, setSensitivityResult] =
    useState<SensitivityResult | null>(null);
  const [activeTab, setActiveTab] = useState<
    'formula' | 'applicability' | 'steps' | 'results' | 'sensitivity'
  >('formula');
  const [productsLoading, setProductsLoading] = useState(true);

  // Load products
  useEffect(() => {
    fetchProducts()
      .then((data) => {
        setProducts(data);
        setProductsLoading(false);
      })
      .catch(() => setProductsLoading(false));
  }, []);

  // Load model metadata when selection changes
  useEffect(() => {
    if (!selectedModelId) return;
    setResult(null);
    setCompareResults(null);
    setError(null);
    fetchModelMeta(selectedModelId)
      .then((meta) => {
        setModelMeta(meta);
        // Set defaults
        const defaults: Record<string, unknown> = {};
        for (const p of meta.parameters) {
          defaults[p.name] = p.default;
        }
        setParams(defaults);
        setSelectedSample('');
        setActiveTab('formula');
      })
      .catch((e) => setError(e.message));
  }, [selectedModelId]);

  const handleSampleChange = useCallback(
    (sampleName: string) => {
      if (!modelMeta || !sampleName) return;
      const sampleParams = modelMeta.samples[sampleName];
      if (sampleParams) {
        setParams({ ...sampleParams });
        setSelectedSample(sampleName);
      }
    },
    [modelMeta],
  );

  const handleCalculate = useCallback(async () => {
    if (!selectedModelId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runCalculation(selectedModelId, params);
      setResult(res);
      setActiveTab('steps');
      setExpandedSteps(new Set(res.calculation_steps.map((s) => s.step_number)));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Calculation failed');
    } finally {
      setLoading(false);
    }
  }, [selectedModelId, params]);

  const handleCompare = useCallback(async () => {
    if (compareModelIds.size < 2) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runComparison([...compareModelIds], params);
      setCompareResults(res);
      setActiveTab('results');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Comparison failed');
    } finally {
      setLoading(false);
    }
  }, [compareModelIds, params]);

  const toggleClass = (ac: string) => {
    setExpandedClasses((prev) => {
      const next = new Set(prev);
      if (next.has(ac)) next.delete(ac);
      else next.add(ac);
      return next;
    });
  };

  const toggleStep = (n: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });
  };

  const toggleCompareModel = (mid: string) => {
    setCompareModelIds((prev) => {
      const next = new Set(prev);
      if (next.has(mid)) next.delete(mid);
      else next.add(mid);
      return next;
    });
  };

  // ── Render ──────────────────────────────────────────────────

  return (
    <div className="flex gap-6 h-[calc(100vh-8rem)]">
      {/* ─── Left Panel: Product / Model Selector ─── */}
      <div className="w-72 flex-shrink-0 bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card flex flex-col">
        <div className="px-4 py-3 border-b border-enterprise-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FlaskConical size={18} className="text-primary-600" />
            <h2 className="text-sm font-semibold text-enterprise-800">
              Models
            </h2>
          </div>
          <button
            onClick={() => {
              setCompareMode(!compareMode);
              setCompareResults(null);
            }}
            className={cn(
              'flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors',
              compareMode
                ? 'bg-primary-100 text-primary-700'
                : 'bg-enterprise-100 text-enterprise-600 hover:bg-enterprise-200',
            )}
          >
            <GitCompare size={12} />
            Compare
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {productsLoading ? (
            <div className="p-4 text-sm text-enterprise-500">Loading...</div>
          ) : Object.keys(products).length === 0 ? (
            <div className="p-4 text-sm text-enterprise-500">
              No models loaded. Start the pricing engine on port 8002.
            </div>
          ) : (
            Object.entries(products).map(([ac, models]) => {
              const config = ASSET_CLASS_CONFIG[ac] || {
                label: ac,
                color: 'text-enterprise-700',
                bg: 'bg-enterprise-50 border-enterprise-200',
              };
              const isExpanded = expandedClasses.has(ac);

              return (
                <div key={ac} className="mb-1">
                  <button
                    onClick={() => toggleClass(ac)}
                    className={cn(
                      'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                      config.color,
                      'hover:bg-enterprise-50',
                    )}
                  >
                    {isExpanded ? (
                      <ChevronDown size={14} />
                    ) : (
                      <ChevronRight size={14} />
                    )}
                    {config.label}
                    <span className="ml-auto text-xs text-enterprise-400">
                      {models.length}
                    </span>
                  </button>

                  {isExpanded && (
                    <div className="ml-3 mt-0.5 space-y-0.5">
                      {models.map((m) => {
                        const isSelected = selectedModelId === m.model_id;
                        const isCompareChecked = compareModelIds.has(
                          m.model_id,
                        );

                        return (
                          <div
                            key={m.model_id}
                            className="flex items-center gap-1.5"
                          >
                            {compareMode && (
                              <input
                                type="checkbox"
                                checked={isCompareChecked}
                                onChange={() => toggleCompareModel(m.model_id)}
                                className="rounded border-enterprise-300 text-primary-600 w-3.5 h-3.5"
                              />
                            )}
                            <button
                              onClick={() => setSelectedModelId(m.model_id)}
                              className={cn(
                                'flex-1 text-left px-3 py-1.5 rounded-lg text-xs transition-all',
                                isSelected
                                  ? 'bg-primary-50 text-primary-700 font-medium border border-primary-200'
                                  : 'text-enterprise-600 hover:bg-enterprise-50',
                              )}
                            >
                              <div className="font-medium">{m.model_name}</div>
                              <div className="text-[10px] text-enterprise-400 mt-0.5">
                                {m.product_type}
                              </div>
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {compareMode && compareModelIds.size >= 2 && (
          <div className="p-2 border-t border-enterprise-100">
            <button
              onClick={handleCompare}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50"
            >
              <GitCompare size={14} />
              Compare {compareModelIds.size} Models
            </button>
          </div>
        )}
      </div>

      {/* ─── Right Panel: Model Detail ─── */}
      <div className="flex-1 overflow-y-auto space-y-4">
        {!selectedModelId ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-enterprise-400">
              <Calculator size={48} className="mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium">
                Select a model to begin
              </p>
              <p className="text-sm mt-1">
                Choose a product and pricing model from the left panel
              </p>
            </div>
          </div>
        ) : !modelMeta ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-enterprise-500">Loading model...</div>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={cn(
                        'px-2 py-0.5 rounded text-[10px] font-semibold uppercase border',
                        ASSET_CLASS_CONFIG[modelMeta.asset_class]?.bg ||
                          'bg-enterprise-50 border-enterprise-200',
                      )}
                    >
                      {modelMeta.asset_class}
                    </span>
                    <span className="text-xs text-enterprise-400">
                      {modelMeta.product_type}
                    </span>
                  </div>
                  <h2 className="text-xl font-bold text-enterprise-900">
                    {modelMeta.model_name}
                  </h2>
                  <p className="text-sm text-enterprise-500 mt-1 max-w-2xl">
                    {modelMeta.short_description}
                  </p>
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-1">
              {(
                [
                  {
                    id: 'formula' as const,
                    label: 'Formula & Theory',
                    icon: BookOpen,
                  },
                  {
                    id: 'applicability' as const,
                    label: 'When to Use',
                    icon: Info,
                  },
                  {
                    id: 'steps' as const,
                    label: 'Calculation Steps',
                    icon: Beaker,
                  },
                  {
                    id: 'results' as const,
                    label: 'Results',
                    icon: BarChart3,
                  },
                  {
                    id: 'sensitivity' as const,
                    label: 'Sensitivity',
                    icon: Activity,
                  },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                    activeTab === tab.id
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-enterprise-500 hover:bg-enterprise-50',
                  )}
                >
                  <tab.icon size={14} />
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            {activeTab === 'formula' && (
              <FormulaTab meta={modelMeta} />
            )}
            {activeTab === 'applicability' && (
              <ApplicabilityTab meta={modelMeta} />
            )}
            {activeTab === 'steps' && result && (
              <StepsTab
                steps={result.calculation_steps}
                expandedSteps={expandedSteps}
                toggleStep={toggleStep}
              />
            )}
            {activeTab === 'results' && (result || compareResults) && (
              <ResultsTab
                result={result}
                compareResults={compareResults}
              />
            )}
            {activeTab === 'sensitivity' && (
              <SensitivityTab
                selectedModelId={selectedModelId}
                compareModelIds={compareModelIds}
                params={params}
                modelMeta={modelMeta}
                sensitivityResult={sensitivityResult}
                setSensitivityResult={setSensitivityResult}
                loading={loading}
                setLoading={(v: boolean) => setLoading(v)}
                setError={(e: string | null) => setError(e)}
              />
            )}

            {/* Parameters + Calculate */}
            <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-enterprise-800">
                  Parameters
                </h3>
                <div className="flex items-center gap-2">
                  <select
                    value={selectedSample}
                    onChange={(e) => handleSampleChange(e.target.value)}
                    className="text-xs border border-enterprise-200 rounded-lg px-2 py-1.5 text-enterprise-600 bg-enterprise-50"
                  >
                    <option value="">Load a sample...</option>
                    {Object.keys(modelMeta.samples).map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={handleCalculate}
                    disabled={loading}
                    className="flex items-center gap-1.5 px-4 py-1.5 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
                  >
                    <Play size={14} />
                    {loading ? 'Calculating...' : 'Calculate'}
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {modelMeta.parameters.map((p) => (
                  <ParameterInput
                    key={p.name}
                    spec={p}
                    value={params[p.name]}
                    onChange={(v) =>
                      setParams((prev) => ({ ...prev, [p.name]: v }))
                    }
                  />
                ))}
              </div>

              {error && (
                <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                  {error}
                </div>
              )}
            </div>

            {/* Show steps/results prompt if no calculation yet */}
            {!result && activeTab === 'steps' && (
              <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-8 text-center">
                <Beaker
                  size={32}
                  className="mx-auto mb-3 text-enterprise-300"
                />
                <p className="text-enterprise-500">
                  Run a calculation to see step-by-step workings
                </p>
              </div>
            )}
            {!result && !compareResults && activeTab === 'results' && (
              <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-8 text-center">
                <BarChart3
                  size={32}
                  className="mx-auto mb-3 text-enterprise-300"
                />
                <p className="text-enterprise-500">
                  Run a calculation to see results
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────

function ParameterInput({
  spec,
  value,
  onChange,
}: {
  spec: ParameterSpec;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (spec.type === 'select' && spec.options) {
    return (
      <div>
        <label className="block text-xs font-medium text-enterprise-600 mb-1">
          {spec.label}
        </label>
        <select
          value={String(value ?? spec.default)}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border border-enterprise-200 rounded-lg px-2.5 py-1.5 text-sm text-enterprise-800 bg-white"
        >
          {spec.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
        <p className="text-[10px] text-enterprise-400 mt-0.5">
          {spec.description}
        </p>
      </div>
    );
  }

  return (
    <div>
      <label className="block text-xs font-medium text-enterprise-600 mb-1">
        {spec.label}
        {spec.unit && (
          <span className="text-enterprise-400 font-normal ml-1">
            ({spec.unit})
          </span>
        )}
      </label>
      <input
        type="number"
        value={value !== undefined && value !== null ? String(value) : ''}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === '' ? spec.default : Number(v));
        }}
        step={spec.step ?? undefined}
        min={spec.min_value ?? undefined}
        max={spec.max_value ?? undefined}
        className="w-full border border-enterprise-200 rounded-lg px-2.5 py-1.5 text-sm text-enterprise-800 bg-white font-mono"
      />
      <p className="text-[10px] text-enterprise-400 mt-0.5">
        {spec.description}
      </p>
    </div>
  );
}

function FormulaTab({ meta }: { meta: ModelMetadata }) {
  return (
    <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5 space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-enterprise-800 mb-2">
          Pricing Formula
        </h3>
        <div className="bg-slate-900 rounded-lg p-4 font-mono text-sm text-green-300 whitespace-pre-wrap overflow-x-auto">
          {meta.formula_plain}
        </div>
        <div className="mt-2 bg-enterprise-50 rounded-lg p-3 font-mono text-xs text-enterprise-600 whitespace-pre-wrap overflow-x-auto border border-enterprise-100">
          <span className="text-enterprise-400">LaTeX: </span>
          {meta.formula_latex}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-enterprise-800 mb-2">
          Description
        </h3>
        <p className="text-sm text-enterprise-600 leading-relaxed">
          {meta.long_description}
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-enterprise-800 mb-2">
          Assumptions
        </h3>
        <ul className="space-y-1">
          {meta.assumptions.map((a, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-enterprise-600">
              <span className="text-enterprise-300 mt-0.5">-</span>
              {a}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ApplicabilityTab({ meta }: { meta: ModelMetadata }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* When to use */}
      <div className="bg-white rounded-xl border border-green-200 shadow-enterprise-card p-5">
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle2 size={16} className="text-green-600" />
          <h3 className="text-sm font-semibold text-green-800">When to Use</h3>
        </div>
        <ul className="space-y-2">
          {meta.when_to_use.map((item, i) => (
            <li
              key={i}
              className="flex items-start gap-2 text-sm text-green-700"
            >
              <CheckCircle2
                size={12}
                className="text-green-500 mt-0.5 flex-shrink-0"
              />
              {item}
            </li>
          ))}
        </ul>
      </div>

      {/* When NOT to use */}
      <div className="bg-white rounded-xl border border-red-200 shadow-enterprise-card p-5">
        <div className="flex items-center gap-2 mb-3">
          <XCircle size={16} className="text-red-600" />
          <h3 className="text-sm font-semibold text-red-800">
            When NOT to Use
          </h3>
        </div>
        <ul className="space-y-2">
          {meta.when_not_to_use.map((item, i) => (
            <li
              key={i}
              className="flex items-start gap-2 text-sm text-red-700"
            >
              <XCircle
                size={12}
                className="text-red-400 mt-0.5 flex-shrink-0"
              />
              {item}
            </li>
          ))}
        </ul>
      </div>

      {/* Limitations */}
      <div className="bg-white rounded-xl border border-amber-200 shadow-enterprise-card p-5 lg:col-span-2">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle size={16} className="text-amber-600" />
          <h3 className="text-sm font-semibold text-amber-800">
            Known Limitations
          </h3>
        </div>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {meta.limitations.map((item, i) => (
            <li
              key={i}
              className="flex items-start gap-2 text-sm text-amber-700"
            >
              <AlertTriangle
                size={12}
                className="text-amber-400 mt-0.5 flex-shrink-0"
              />
              {item}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function StepsTab({
  steps,
  expandedSteps,
  toggleStep,
}: {
  steps: CalculationStep[];
  expandedSteps: Set<number>;
  toggleStep: (n: number) => void;
}) {
  return (
    <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
      <h3 className="text-sm font-semibold text-enterprise-800 mb-3">
        Step-by-Step Calculation
      </h3>
      <div className="space-y-2">
        {steps.map((step) => {
          const isExpanded = expandedSteps.has(step.step_number);
          return (
            <div
              key={step.step_number}
              className="border border-enterprise-100 rounded-lg overflow-hidden"
            >
              <button
                onClick={() => toggleStep(step.step_number)}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-enterprise-50 transition-colors"
              >
                <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary-100 text-primary-700 text-xs font-bold flex-shrink-0">
                  {step.step_number}
                </span>
                <span className="text-sm font-medium text-enterprise-800 flex-1">
                  {step.label}
                </span>
                <span className="font-mono text-sm text-primary-600 font-medium">
                  = {typeof step.result === 'number' ? step.result.toFixed(4) : step.result}
                </span>
                {isExpanded ? (
                  <ChevronDown size={14} className="text-enterprise-400" />
                ) : (
                  <ChevronRight size={14} className="text-enterprise-400" />
                )}
              </button>

              {isExpanded && (
                <div className="px-4 pb-3 space-y-2 border-t border-enterprise-100 bg-enterprise-50/50">
                  {step.formula && (
                    <div className="mt-2">
                      <span className="text-[10px] uppercase tracking-wider text-enterprise-400 font-semibold">
                        Formula
                      </span>
                      <div className="font-mono text-xs text-slate-700 bg-white rounded px-2 py-1.5 border border-enterprise-100 mt-0.5">
                        {step.formula}
                      </div>
                    </div>
                  )}
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-enterprise-400 font-semibold">
                      Substitution
                    </span>
                    <div className="font-mono text-xs text-enterprise-700 bg-white rounded px-2 py-1.5 border border-enterprise-100 mt-0.5 whitespace-pre-wrap">
                      {step.substitution}
                    </div>
                  </div>
                  {step.explanation && (
                    <p className="text-xs text-enterprise-500 italic">
                      {step.explanation}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ResultsTab({
  result,
  compareResults,
}: {
  result: CalcResult | null;
  compareResults: {
    results: CalcResult[];
    comparison: Record<string, unknown>;
  } | null;
}) {
  // Compare mode
  if (compareResults) {
    const comp = compareResults.comparison as {
      prices?: Record<string, number>;
      model_reserve?: number;
      greeks?: Record<
        string,
        { values: Record<string, number>; spread: number }
      >;
    };

    return (
      <div className="space-y-4">
        <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
          <h3 className="text-sm font-semibold text-enterprise-800 mb-3">
            Model Comparison
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-enterprise-200">
                  <th className="text-left py-2 text-enterprise-500 font-medium"></th>
                  {compareResults.results.map((r) => (
                    <th
                      key={r.model_id}
                      className="text-right py-2 px-3 text-enterprise-700 font-semibold"
                    >
                      {r.model_name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-enterprise-100">
                  <td className="py-2 text-enterprise-600 font-medium">
                    Fair Value
                  </td>
                  {compareResults.results.map((r) => (
                    <td
                      key={r.model_id}
                      className="text-right py-2 px-3 font-mono font-bold text-enterprise-900"
                    >
                      ${r.fair_value.toFixed(4)}
                    </td>
                  ))}
                </tr>
                {/* Greeks rows */}
                {comp.greeks &&
                  Object.entries(comp.greeks).map(([gname, gdata]) => (
                    <tr
                      key={gname}
                      className="border-b border-enterprise-50"
                    >
                      <td className="py-1.5 text-enterprise-500 capitalize">
                        {gname}
                      </td>
                      {compareResults.results.map((r) => (
                        <td
                          key={r.model_id}
                          className="text-right py-1.5 px-3 font-mono text-xs text-enterprise-600"
                        >
                          {(gdata.values[r.model_id] ?? 0).toFixed(6)}
                        </td>
                      ))}
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          {comp.model_reserve !== undefined && (
            <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <span className="text-sm font-semibold text-amber-800">
                Model Reserve (max - min):{' '}
              </span>
              <span className="font-mono text-amber-900 font-bold">
                ${comp.model_reserve.toFixed(4)}
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Single result
  if (!result) return null;

  const diag = result.diagnostics as Record<string, unknown>;
  const histogram = diag.histogram as
    | { bin_start: number; bin_end: number; count: number }[]
    | undefined;

  return (
    <div className="space-y-4">
      {/* Main result */}
      <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-enterprise-800">
            Pricing Result
          </h3>
          <span className="text-xs text-enterprise-400">{result.method}</span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="bg-primary-50 rounded-lg p-3 border border-primary-200">
            <div className="text-xs text-primary-600 font-medium">
              Fair Value
            </div>
            <div className="text-2xl font-bold text-primary-900 font-mono">
              ${result.fair_value.toFixed(4)}
            </div>
          </div>

          {Object.entries(result.greeks).map(([name, val]) => (
            <div
              key={name}
              className="bg-enterprise-50 rounded-lg p-3 border border-enterprise-100"
            >
              <div className="text-xs text-enterprise-500 font-medium capitalize">
                {name}
              </div>
              <div className="text-lg font-bold text-enterprise-800 font-mono">
                {val >= 0 ? '+' : ''}
                {val.toFixed(6)}
              </div>
            </div>
          ))}
        </div>

        {/* Diagnostics */}
        {Object.keys(diag).length > 0 && !histogram && (
          <div>
            <h4 className="text-xs font-semibold text-enterprise-500 uppercase tracking-wider mb-2">
              Diagnostics
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {Object.entries(diag)
                .filter(
                  ([k]) =>
                    typeof diag[k] === 'number' || typeof diag[k] === 'string',
                )
                .map(([k, v]) => (
                  <div key={k} className="text-xs">
                    <span className="text-enterprise-400">{k}: </span>
                    <span className="font-mono text-enterprise-700">
                      {typeof v === 'number' ? v.toFixed(4) : String(v)}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>

      {/* Hedge simulator histogram */}
      {histogram && histogram.length > 0 && (
        <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
          <h3 className="text-sm font-semibold text-enterprise-800 mb-3">
            Hedge P&L Distribution
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={histogram.map((h) => ({
                  bin: `${h.bin_start.toFixed(1)}`,
                  count: h.count,
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="bin"
                  tick={{ fontSize: 10 }}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 grid grid-cols-3 md:grid-cols-5 gap-3 text-xs">
            {[
              ['Mean P&L', diag.mean_pnl],
              ['Std Dev', diag.std_pnl],
              ['5th Pct', diag.percentile_5],
              ['Median', diag.median_pnl],
              ['95th Pct', diag.percentile_95],
            ].map(([label, val]) => (
              <div key={String(label)}>
                <span className="text-enterprise-400">{String(label)}: </span>
                <span className="font-mono font-medium text-enterprise-700">
                  {typeof val === 'number' ? val.toFixed(2) : '-'}
                </span>
              </div>
            ))}
          </div>
          {diag.verdict && (
            <div
              className={cn(
                'mt-3 p-2 rounded-lg text-sm font-medium',
                String(diag.verdict).includes('GOOD')
                  ? 'bg-green-50 text-green-700 border border-green-200'
                  : 'bg-amber-50 text-amber-700 border border-amber-200',
              )}
            >
              {String(diag.verdict)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Sensitivity Tab ──────────────────────────────────────────

const CHART_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

function SensitivityTab({
  selectedModelId,
  compareModelIds,
  params,
  modelMeta,
  sensitivityResult,
  setSensitivityResult,
  loading,
  setLoading,
  setError,
}: {
  selectedModelId: string | null;
  compareModelIds: Set<string>;
  params: Record<string, unknown>;
  modelMeta: ModelMetadata | null;
  sensitivityResult: SensitivityResult | null;
  setSensitivityResult: (r: SensitivityResult | null) => void;
  loading: boolean;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
}) {
  const [sweepParam, setSweepParam] = useState<string>('');
  const [sweepMin, setSweepMin] = useState<number>(0);
  const [sweepMax, setSweepMax] = useState<number>(1);
  const [sweepSteps, setSweepSteps] = useState<number>(20);
  const [showDelta, setShowDelta] = useState(false);

  const numericParams = (modelMeta?.parameters ?? []).filter(
    (p) => p.type === 'float' || p.type === 'int',
  );

  // Auto-set bounds when sweep param changes
  useEffect(() => {
    if (!sweepParam || !modelMeta) return;
    const spec = modelMeta.parameters.find((p) => p.name === sweepParam);
    if (!spec) return;
    const current = Number(params[sweepParam] ?? spec.default);
    const lo = spec.min_value ?? current * 0.5;
    const hi = spec.max_value ?? current * 1.5;
    setSweepMin(Number(lo.toFixed(4)));
    setSweepMax(Number(hi.toFixed(4)));
  }, [sweepParam, modelMeta, params]);

  const modelIds = compareModelIds.size >= 2
    ? [...compareModelIds]
    : selectedModelId
      ? [selectedModelId]
      : [];

  const handleRun = async () => {
    if (!sweepParam || modelIds.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runSensitivity(
        modelIds,
        params,
        sweepParam,
        sweepMin,
        sweepMax,
        sweepSteps,
      );
      setSensitivityResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sensitivity failed');
    } finally {
      setLoading(false);
    }
  };

  // Build chart data
  const chartData = sensitivityResult
    ? sensitivityResult.sweep_values.map((val, i) => {
        const point: Record<string, unknown> = { x: val };
        for (const [mid, mdata] of Object.entries(sensitivityResult.models)) {
          if (showDelta) {
            point[mid] = mdata.deltas[i];
          } else {
            point[mid] = mdata.prices[i];
          }
        }
        if (!showDelta) {
          point['model_reserve'] = sensitivityResult.model_reserve[i];
        }
        return point;
      })
    : [];

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
        <h3 className="text-sm font-semibold text-enterprise-800 mb-3">
          Parameter Sensitivity Sweep
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div>
            <label className="block text-xs font-medium text-enterprise-600 mb-1">
              Sweep Parameter
            </label>
            <select
              value={sweepParam}
              onChange={(e) => setSweepParam(e.target.value)}
              className="w-full border border-enterprise-200 rounded-lg px-2.5 py-1.5 text-sm bg-white"
            >
              <option value="">Select...</option>
              {numericParams.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-enterprise-600 mb-1">
              Min
            </label>
            <input
              type="number"
              value={sweepMin}
              onChange={(e) => setSweepMin(Number(e.target.value))}
              className="w-full border border-enterprise-200 rounded-lg px-2.5 py-1.5 text-sm font-mono"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-enterprise-600 mb-1">
              Max
            </label>
            <input
              type="number"
              value={sweepMax}
              onChange={(e) => setSweepMax(Number(e.target.value))}
              className="w-full border border-enterprise-200 rounded-lg px-2.5 py-1.5 text-sm font-mono"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-enterprise-600 mb-1">
              Steps
            </label>
            <input
              type="number"
              value={sweepSteps}
              min={3}
              max={100}
              onChange={(e) => setSweepSteps(Number(e.target.value))}
              className="w-full border border-enterprise-200 rounded-lg px-2.5 py-1.5 text-sm font-mono"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={handleRun}
              disabled={loading || !sweepParam || modelIds.length === 0}
              className="w-full flex items-center justify-center gap-1.5 px-4 py-1.5 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              <Activity size={14} />
              {loading ? 'Running...' : 'Run Sweep'}
            </button>
          </div>
        </div>
        {modelIds.length === 0 && (
          <p className="text-xs text-amber-600 mt-2">
            Select a model or enable Compare mode and select 2+ models.
          </p>
        )}
      </div>

      {/* Chart */}
      {sensitivityResult && chartData.length > 0 && (
        <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-enterprise-800">
              {showDelta ? 'Delta' : 'Price'} vs {sensitivityResult.sweep_param}
            </h3>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowDelta(false)}
                className={cn(
                  'px-3 py-1 rounded text-xs font-medium transition-colors',
                  !showDelta
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-enterprise-100 text-enterprise-500 hover:bg-enterprise-200',
                )}
              >
                Price
              </button>
              <button
                onClick={() => setShowDelta(true)}
                className={cn(
                  'px-3 py-1 rounded text-xs font-medium transition-colors',
                  showDelta
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-enterprise-100 text-enterprise-500 hover:bg-enterprise-200',
                )}
              >
                Delta
              </button>
            </div>
          </div>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="x"
                  tick={{ fontSize: 10 }}
                  label={{
                    value: sensitivityResult.sweep_param,
                    position: 'insideBottom',
                    offset: -5,
                    fontSize: 11,
                  }}
                />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip
                  formatter={(value: number) =>
                    typeof value === 'number' ? value.toFixed(4) : value
                  }
                />
                <Legend />
                {Object.entries(sensitivityResult.models).map(
                  ([mid, mdata], i) => (
                    <Line
                      key={mid}
                      type="monotone"
                      dataKey={mid}
                      name={mdata.model_name}
                      stroke={CHART_COLORS[i % CHART_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                    />
                  ),
                )}
                {!showDelta && Object.keys(sensitivityResult.models).length > 1 && (
                  <Line
                    type="monotone"
                    dataKey="model_reserve"
                    name="Model Reserve"
                    stroke="#dc2626"
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    dot={false}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Summary stats */}
      {sensitivityResult && Object.keys(sensitivityResult.models).length > 1 && (
        <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card p-5">
          <h3 className="text-sm font-semibold text-enterprise-800 mb-3">
            Model Reserve Summary
          </h3>
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-amber-50 rounded-lg p-3 border border-amber-200">
              <div className="text-xs text-amber-600 font-medium">
                Max Reserve
              </div>
              <div className="text-lg font-bold text-amber-900 font-mono">
                $
                {Math.max(...sensitivityResult.model_reserve.filter((v) => v !== null)).toFixed(4)}
              </div>
            </div>
            <div className="bg-enterprise-50 rounded-lg p-3 border border-enterprise-100">
              <div className="text-xs text-enterprise-500 font-medium">
                Avg Reserve
              </div>
              <div className="text-lg font-bold text-enterprise-800 font-mono">
                $
                {(
                  sensitivityResult.model_reserve
                    .filter((v) => v !== null)
                    .reduce((a, b) => a + b, 0) /
                  sensitivityResult.model_reserve.filter((v) => v !== null).length
                ).toFixed(4)}
              </div>
            </div>
            <div className="bg-enterprise-50 rounded-lg p-3 border border-enterprise-100">
              <div className="text-xs text-enterprise-500 font-medium">
                Min Reserve
              </div>
              <div className="text-lg font-bold text-enterprise-800 font-mono">
                $
                {Math.min(...sensitivityResult.model_reserve.filter((v) => v !== null)).toFixed(4)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
