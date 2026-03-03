import { useState } from 'react';
import {
  Settings,
  Bell,
  Palette,
  Shield,
  Database,
  Clock,
  Monitor,
  Save,
  RefreshCw,
  CheckCircle,
  Server,
} from 'lucide-react';
import { Card } from '../shared/Card';
import { Button, Badge } from '../shared/Button';
import { cn } from '@/utils/format';

interface SettingsState {
  // Display
  theme: 'light' | 'dark' | 'system';
  compactMode: boolean;
  showGreeks: boolean;
  defaultCurrency: string;
  numberFormat: 'standard' | 'compact';

  // Notifications
  emailAlerts: boolean;
  breachNotifications: boolean;
  escalationAlerts: boolean;
  reportCompletionAlerts: boolean;

  // IPV Configuration
  amberThresholdPct: number;
  redThresholdPct: number;
  autoRunSchedule: string;
  defaultAssetClasses: string[];

  // Data Refresh
  autoRefresh: boolean;
  refreshInterval: number;
  staleDatatWarningMinutes: number;
}

const defaultSettings: SettingsState = {
  theme: 'light',
  compactMode: false,
  showGreeks: true,
  defaultCurrency: 'USD',
  numberFormat: 'standard',

  emailAlerts: true,
  breachNotifications: true,
  escalationAlerts: true,
  reportCompletionAlerts: false,

  amberThresholdPct: 2.0,
  redThresholdPct: 5.0,
  autoRunSchedule: '17:00',
  defaultAssetClasses: ['FX Spot', 'FX Forward', 'FX Option'],

  autoRefresh: true,
  refreshInterval: 60,
  staleDatatWarningMinutes: 30,
};

const CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF'];
const ALL_ASSET_CLASSES = [
  'FX Spot',
  'FX Forward',
  'FX Option',
  'IR Swap',
  'Credit',
  'Equity',
  'Commodity',
];

type TabId = 'display' | 'notifications' | 'ipv' | 'data' | 'system';

const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'display', label: 'Display', icon: <Palette size={16} /> },
  { id: 'notifications', label: 'Notifications', icon: <Bell size={16} /> },
  { id: 'ipv', label: 'IPV Configuration', icon: <Shield size={16} /> },
  { id: 'data', label: 'Data & Refresh', icon: <Database size={16} /> },
  { id: 'system', label: 'System Info', icon: <Server size={16} /> },
];

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('display');
  const [settings, setSettings] = useState<SettingsState>(defaultSettings);
  const [saved, setSaved] = useState(false);

  const updateSetting = <K extends keyof SettingsState>(
    key: K,
    value: SettingsState[K]
  ) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const toggleAssetClass = (ac: string) => {
    setSettings((prev) => ({
      ...prev,
      defaultAssetClasses: prev.defaultAssetClasses.includes(ac)
        ? prev.defaultAssetClasses.filter((x) => x !== ac)
        : [...prev.defaultAssetClasses, ac],
    }));
    setSaved(false);
  };

  const handleSave = () => {
    localStorage.setItem('vc-settings', JSON.stringify(settings));
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const handleReset = () => {
    setSettings(defaultSettings);
    setSaved(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-primary-100 rounded-lg">
            <Settings size={22} className="text-primary-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-enterprise-800">Settings</h2>
            <p className="text-sm text-enterprise-500">Configure dashboard preferences and system parameters</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {saved && (
            <span className="flex items-center gap-1.5 text-sm text-green-600">
              <CheckCircle size={16} />
              Saved
            </span>
          )}
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={handleReset}>
            Reset Defaults
          </Button>
          <Button size="sm" icon={<Save size={14} />} onClick={handleSave}>
            Save Settings
          </Button>
        </div>
      </div>

      <div className="flex gap-6">
        {/* Sidebar Tabs */}
        <div className="w-56 shrink-0">
          <nav className="space-y-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-150',
                  activeTab === tab.id
                    ? 'bg-primary-50 text-primary-700 border border-primary-200'
                    : 'text-enterprise-600 hover:bg-enterprise-100 hover:text-enterprise-800'
                )}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1 space-y-6">
          {activeTab === 'display' && (
            <>
              <Card title="Appearance">
                <div className="space-y-6">
                  {/* Theme */}
                  <div>
                    <label className="block text-sm font-semibold text-enterprise-700 mb-3">
                      Theme
                    </label>
                    <div className="flex gap-3">
                      {(['light', 'dark', 'system'] as const).map((theme) => (
                        <button
                          key={theme}
                          onClick={() => updateSetting('theme', theme)}
                          className={cn(
                            'flex items-center gap-2 px-4 py-2.5 rounded-lg border transition-all',
                            settings.theme === theme
                              ? 'bg-primary-50 border-primary-300 text-primary-700'
                              : 'bg-white border-enterprise-300 text-enterprise-600 hover:border-enterprise-400'
                          )}
                        >
                          {theme === 'light' && <Palette size={16} />}
                          {theme === 'dark' && <Monitor size={16} />}
                          {theme === 'system' && <Monitor size={16} />}
                          <span className="capitalize font-medium">{theme}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Compact Mode */}
                  <ToggleRow
                    label="Compact Mode"
                    description="Reduce spacing and font sizes for denser information display"
                    checked={settings.compactMode}
                    onChange={(v) => updateSetting('compactMode', v)}
                  />

                  {/* Show Greeks */}
                  <ToggleRow
                    label="Show Greeks in Position Detail"
                    description="Display Delta, Gamma, Vega, Theta in position views"
                    checked={settings.showGreeks}
                    onChange={(v) => updateSetting('showGreeks', v)}
                  />
                </div>
              </Card>

              <Card title="Number Formatting">
                <div className="space-y-6">
                  {/* Currency */}
                  <div>
                    <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                      Default Display Currency
                    </label>
                    <select
                      value={settings.defaultCurrency}
                      onChange={(e) => updateSetting('defaultCurrency', e.target.value)}
                      className="w-48 px-3 py-2.5 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    >
                      {CURRENCIES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>

                  {/* Number Format */}
                  <div>
                    <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                      Number Format
                    </label>
                    <div className="flex gap-3">
                      <button
                        onClick={() => updateSetting('numberFormat', 'standard')}
                        className={cn(
                          'px-4 py-2.5 rounded-lg border transition-all',
                          settings.numberFormat === 'standard'
                            ? 'bg-primary-50 border-primary-300 text-primary-700'
                            : 'bg-white border-enterprise-300 text-enterprise-600 hover:border-enterprise-400'
                        )}
                      >
                        <span className="font-medium">1,234,567.89</span>
                        <p className="text-xs text-enterprise-500 mt-0.5">Standard</p>
                      </button>
                      <button
                        onClick={() => updateSetting('numberFormat', 'compact')}
                        className={cn(
                          'px-4 py-2.5 rounded-lg border transition-all',
                          settings.numberFormat === 'compact'
                            ? 'bg-primary-50 border-primary-300 text-primary-700'
                            : 'bg-white border-enterprise-300 text-enterprise-600 hover:border-enterprise-400'
                        )}
                      >
                        <span className="font-medium">$1.23M</span>
                        <p className="text-xs text-enterprise-500 mt-0.5">Compact</p>
                      </button>
                    </div>
                  </div>
                </div>
              </Card>
            </>
          )}

          {activeTab === 'notifications' && (
            <Card title="Alert Preferences">
              <div className="space-y-5">
                <ToggleRow
                  label="Email Alerts"
                  description="Receive email notifications for critical valuation events"
                  checked={settings.emailAlerts}
                  onChange={(v) => updateSetting('emailAlerts', v)}
                />
                <ToggleRow
                  label="Tolerance Breach Notifications"
                  description="Alert when positions breach AMBER or RED thresholds"
                  checked={settings.breachNotifications}
                  onChange={(v) => updateSetting('breachNotifications', v)}
                />
                <ToggleRow
                  label="Escalation Alerts"
                  description="Notify when exceptions are auto-escalated to manager or committee"
                  checked={settings.escalationAlerts}
                  onChange={(v) => updateSetting('escalationAlerts', v)}
                />
                <ToggleRow
                  label="Report Completion Alerts"
                  description="Notify when regulatory reports finish generating"
                  checked={settings.reportCompletionAlerts}
                  onChange={(v) => updateSetting('reportCompletionAlerts', v)}
                />
              </div>
            </Card>
          )}

          {activeTab === 'ipv' && (
            <>
              <Card title="Tolerance Thresholds">
                <div className="space-y-6">
                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-semibold text-amber-700 mb-2">
                        AMBER Threshold (%)
                      </label>
                      <div className="flex items-center gap-3">
                        <input
                          type="number"
                          step="0.1"
                          min="0"
                          max="100"
                          value={settings.amberThresholdPct}
                          onChange={(e) => updateSetting('amberThresholdPct', parseFloat(e.target.value))}
                          className="w-32 px-3 py-2.5 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
                        />
                        <span className="text-sm text-enterprise-500">
                          Desk mark vs VC fair value difference
                        </span>
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-semibold text-red-700 mb-2">
                        RED Threshold (%)
                      </label>
                      <div className="flex items-center gap-3">
                        <input
                          type="number"
                          step="0.1"
                          min="0"
                          max="100"
                          value={settings.redThresholdPct}
                          onChange={(e) => updateSetting('redThresholdPct', parseFloat(e.target.value))}
                          className="w-32 px-3 py-2.5 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
                        />
                        <span className="text-sm text-enterprise-500">
                          Triggers mandatory investigation
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 bg-enterprise-50 rounded-lg border border-enterprise-200">
                    <p className="text-sm text-enterprise-600">
                      Positions with |Desk Mark - VC Fair Value| / Fair Value between AMBER and RED thresholds
                      are flagged for review. Above RED requires escalation within 24 hours.
                    </p>
                  </div>
                </div>
              </Card>

              <Card title="IPV Run Schedule">
                <div className="space-y-6">
                  <div>
                    <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                      Auto-Run Time (daily)
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="time"
                        value={settings.autoRunSchedule}
                        onChange={(e) => updateSetting('autoRunSchedule', e.target.value)}
                        className="px-3 py-2.5 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                      <Clock size={16} className="text-enterprise-400" />
                      <span className="text-sm text-enterprise-500">UTC</span>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-enterprise-700 mb-3">
                      Default Asset Classes for IPV
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {ALL_ASSET_CLASSES.map((ac) => (
                        <button
                          key={ac}
                          onClick={() => toggleAssetClass(ac)}
                          className={cn(
                            'px-4 py-2 rounded-lg text-sm font-medium border transition-all',
                            settings.defaultAssetClasses.includes(ac)
                              ? 'bg-primary-600 border-primary-600 text-white'
                              : 'bg-white border-enterprise-300 text-enterprise-600 hover:border-primary-400'
                          )}
                        >
                          {ac}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </Card>
            </>
          )}

          {activeTab === 'data' && (
            <Card title="Data Refresh">
              <div className="space-y-6">
                <ToggleRow
                  label="Auto-Refresh Dashboard"
                  description="Automatically poll backend APIs for updated data"
                  checked={settings.autoRefresh}
                  onChange={(v) => updateSetting('autoRefresh', v)}
                />

                {settings.autoRefresh && (
                  <div>
                    <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                      Refresh Interval (seconds)
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="number"
                        min="10"
                        max="600"
                        step="10"
                        value={settings.refreshInterval}
                        onChange={(e) => updateSetting('refreshInterval', parseInt(e.target.value, 10))}
                        className="w-32 px-3 py-2.5 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                      <span className="text-sm text-enterprise-500">
                        seconds between API polls
                      </span>
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                    Stale Data Warning (minutes)
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="number"
                      min="5"
                      max="120"
                      step="5"
                      value={settings.staleDatatWarningMinutes}
                      onChange={(e) => updateSetting('staleDatatWarningMinutes', parseInt(e.target.value, 10))}
                      className="w-32 px-3 py-2.5 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                    <span className="text-sm text-enterprise-500">
                      Show warning if data older than this
                    </span>
                  </div>
                </div>
              </div>
            </Card>
          )}

          {activeTab === 'system' && (
            <Card title="System Information">
              <div className="space-y-4">
                <SystemInfoRow label="Application" value="Valuation Control Dashboard" />
                <SystemInfoRow label="Version" value="1.0.0" />
                <SystemInfoRow label="Environment" value="Development" />
                <SystemInfoRow label="Backend (Agent 7)" value="http://localhost:8007" />

                <div className="pt-4 border-t border-enterprise-200">
                  <h4 className="text-sm font-semibold text-enterprise-700 mb-3">Upstream Services</h4>
                  <div className="space-y-2">
                    <ServiceRow name="Agent 1 -- Data Layer" port="8000" />
                    <ServiceRow name="Agent 2 -- Pricing Engine" port="8002" />
                    <ServiceRow name="Agent 3 -- IPV Orchestrator" port="8003" />
                    <ServiceRow name="Agent 4 -- Dispute Workflow" port="8004" />
                    <ServiceRow name="Agent 5 -- Reserve Calculations" port="8005" />
                    <ServiceRow name="Agent 6 -- Regulatory Reporting" port="8006" />
                    <ServiceRow name="Agent 8 -- Validation" port="8008" />
                  </div>
                </div>

                <div className="pt-4 border-t border-enterprise-200">
                  <h4 className="text-sm font-semibold text-enterprise-700 mb-3">Regulatory Coverage</h4>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="blue" size="sm">Basel III / CRD IV</Badge>
                    <Badge variant="blue" size="sm">IFRS 13</Badge>
                    <Badge variant="blue" size="sm">PRA110 (UK)</Badge>
                    <Badge variant="blue" size="sm">FR Y-14Q (US)</Badge>
                    <Badge variant="green" size="sm">SOX Audit Trail</Badge>
                  </div>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <p className="text-sm font-medium text-enterprise-800">{label}</p>
        <p className="text-xs text-enterprise-500 mt-0.5">{description}</p>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200',
          checked ? 'bg-primary-600' : 'bg-enterprise-300'
        )}
      >
        <span
          className={cn(
            'inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200',
            checked ? 'translate-x-5' : 'translate-x-0'
          )}
        />
      </button>
    </div>
  );
}

function SystemInfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-2 border-b border-enterprise-100">
      <span className="text-sm text-enterprise-500">{label}</span>
      <span className="text-sm font-medium text-enterprise-800">{value}</span>
    </div>
  );
}

function ServiceRow({ name, port }: { name: string; port: string }) {
  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-enterprise-50">
      <span className="text-sm text-enterprise-700">{name}</span>
      <div className="flex items-center gap-2">
        <span className="text-xs font-mono text-enterprise-500">:{port}</span>
        <div className="w-2 h-2 rounded-full bg-enterprise-300" />
      </div>
    </div>
  );
}
