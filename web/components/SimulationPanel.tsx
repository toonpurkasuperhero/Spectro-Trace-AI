'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  FlaskConical,
  Sliders,
  AlertTriangle,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
  Eye,
  Layers,
  SplitSquareVertical,
  Cpu,
  Info,
  ExternalLink,
  ChevronRight,
  Flame,
  CloudRain,
  Sun,
  ShieldAlert,
  Lock
} from 'lucide-react';
import GenerativeBanner from '@/components/GenerativeBanner';

interface SimulationModel {
  id: string;
  family?: string;
  tier?: string;
  mode: string;
  label: string;
  cost_hint: string;
  description: string;
}

interface SimulationVariant {
  idx: number;
  url: string;
  width: number;
  height: number;
  edge_fidelity_ssim: number;
  scenario: string;
  severity: number;
  label: string;
}

interface SimulationRecord {
  id: string;
  job_id: string;
  status: 'queued' | 'generating' | 'done' | 'done_partial' | 'failed';
  scenario: string;
  severity: number;
  model_requested: string;
  model_used?: string;
  prompt_text: string;
  prompt_version?: string;
  variants: SimulationVariant[];
  error?: string;
  created_at: number;
}

interface SimulationPanelProps {
  jobId: string;
  module: string;
  mode?: string;
  rawImageUrl: string;
  apiBase?: string;
}

const SCENARIOS = [
  {
    id: 'corrosion',
    title: 'Surface Corrosion',
    icon: Flame,
    desc: 'Oxidation, rust pitting, and patina on industrial metallic surfaces.',
    applicableModules: ['print', 'specimen', 'thermal']
  },
  {
    id: 'humidity',
    title: 'High Humidity Damage',
    icon: CloudRain,
    desc: 'Moisture condensation droplets, damp staining, and specular glints.',
    applicableModules: ['thermal', 'print', 'specimen']
  },
  {
    id: 'thermal_cycling',
    title: 'Thermal Cycling Wear',
    icon: Sliders,
    desc: 'Micro-cracking lines and boundary warping from rapid temperature swings.',
    applicableModules: ['print', 'specimen', 'thermal']
  },
  {
    id: 'weathering',
    title: 'Environmental Weathering',
    icon: Sun,
    desc: 'Sun UV fading, pigment chalking, and long-term exterior degradation.',
    applicableModules: ['thermal', 'print', 'specimen']
  },
  {
    id: 'micro_fracture',
    title: 'Micro-Fracture Propagation',
    icon: Sliders,
    desc: 'Simulation of micro-crack growth under cyclical mechanical stress.',
    applicableModules: ['specimen', 'print', 'thermal']
  },
  {
    id: 'delamination',
    title: 'Layer Delamination',
    icon: Layers,
    desc: 'Separation of material layers due to adhesion failure.',
    applicableModules: ['print', 'specimen', 'thermal']
  }
];

const SEVERITY_LABELS: Record<number, string> = {
  1: 'Faint (1)',
  2: 'Light (2)',
  3: 'Moderate (3)',
  4: 'Heavy (4)',
  5: 'Severe (5)'
};

export default function SimulationPanel({
  jobId,
  module,
  mode = '*',
  rawImageUrl,
  apiBase = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
}: SimulationPanelProps) {
  const [models, setModels] = useState<SimulationModel[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>('corrosion');
  const [severity, setSeverity] = useState<number>(3);
  const [selectedModel, setSelectedModel] = useState<string>('auto');
  const [variantsCount, setVariantsCount] = useState<number>(1);
  const [userNote, setUserNote] = useState<string>('');

  const [activeSimulation, setActiveSimulation] = useState<SimulationRecord | null>(null);
  const [simHistory, setSimHistory] = useState<SimulationRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Compare slider state for chosen variant
  const [activeVariantIdx, setActiveVariantIdx] = useState<number>(0);
  const [sliderPos, setSliderPos] = useState<number>(50);
  const [compareMode, setCompareMode] = useState<'slider' | 'sim_only' | 'raw_only'>('slider');
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef<boolean>(false);

  // Policy restrictions
  const isHistology = module === 'specimen' && mode === 'histology';
  const isAudio = module === 'audio';
  const isPolicyBlocked = isAudio || isHistology;

  // 1. Fetch available models and existing simulation runs for this job
  useEffect(() => {
    async function init() {
      try {
        const mRes = await fetch(`${apiBase}/sim/models`);
        if (mRes.ok) {
          const mData = await mRes.json();
          setModels(mData.models || []);
        }

        const hRes = await fetch(`${apiBase}/jobs/${jobId}/simulations`);
        if (hRes.ok) {
          const hData = await hRes.json();
          const sims: SimulationRecord[] = hData.simulations || [];
          setSimHistory(sims);
          if (sims.length > 0) {
            setActiveSimulation(sims[sims.length - 1]);
          }
        }
      } catch (err) {
        console.error('Failed to load simulation models or history:', err);
      }
    }

    if (!isPolicyBlocked && jobId) {
      init();
    }
  }, [jobId, apiBase, isPolicyBlocked]);

  // Adjust default scenario to match module
  useEffect(() => {
    if (module === 'thermal') {
      setSelectedScenario('weathering');
    } else {
      setSelectedScenario('corrosion');
    }
  }, [module]);

  // 2. Poll simulation execution
  const pollSimulation = async (simId: string) => {
    const maxPolls = 30;
    for (let i = 0; i < maxPolls; i++) {
      await new Promise(r => setTimeout(r, 1200));
      try {
        const res = await fetch(`${apiBase}/simulations/${simId}`);
        if (res.ok) {
          const sim: SimulationRecord = await res.json();
          setActiveSimulation(sim);
          if (sim.status === 'done' || sim.status === 'done_partial' || sim.status === 'failed') {
            setLoading(false);
            // Refresh history
            const hRes = await fetch(`${apiBase}/jobs/${jobId}/simulations`);
            if (hRes.ok) {
              const hData = await hRes.json();
              setSimHistory(hData.simulations || []);
            }
            return;
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }
    setLoading(false);
  };

  // 3. Trigger new simulation
  const handleTriggerSimulation = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/jobs/${jobId}/simulations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: selectedScenario,
          severity,
          model: selectedModel,
          variants: variantsCount,
          user_note: userNote.trim() || undefined
        })
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Failed to trigger simulation');
      }

      const initialRecord: SimulationRecord = await res.json();
      setActiveSimulation(initialRecord);
      pollSimulation(initialRecord.id);
    } catch (err: any) {
      setError(err.message || 'Error executing simulation');
      setLoading(false);
    }
  };

  // Slider drag controls
  const handleMouseDown = () => { isDragging.current = true; };
  const handleTouchStart = () => { isDragging.current = true; };
  const handleMouseUp = () => { isDragging.current = false; };
  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    setSliderPos((x / rect.width) * 100);
  };
  const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
    if (!isDragging.current || !containerRef.current || !e.touches[0]) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.touches[0].clientX - rect.left, rect.width));
    setSliderPos((x / rect.width) * 100);
  };

  if (isPolicyBlocked) {
    return (
      <div className="bg-slate-900/60 border border-white/10 rounded-2xl p-6 text-center space-y-3">
        <ShieldAlert size={36} className="text-amber-400 mx-auto opacity-80" />
        <h3 className="text-sm font-semibold text-white">Simulation Lab Disabled by Clinical / Physical Policy</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
          {isAudio
            ? 'Simulation Lab is not available for acoustic spectrograms as hypothetical signal frequencies cannot be fabricated.'
            : 'Simulation Lab is strictly prohibited on medical histology specimens. Specimen evaluation requires strictly deterministic observation.'}
        </p>
      </div>
    );
  }

  const currentVariant = activeSimulation?.variants?.[activeVariantIdx] || activeSimulation?.variants?.[0];

  return (
    <div className="space-y-5">
      {/* 1. Mandatory positioning banner */}
      <GenerativeBanner message="AI illustration of a hypothetical scenario. Not a prediction, not a durability estimate, not used by analysis." />

      {/* 2. Simulation Configuration Form */}
      <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-5 space-y-5 w-full overflow-hidden">
        <div className="flex items-center justify-between border-b border-white/10 pb-3 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <FlaskConical size={16} className="text-violet-400" />
            <h3 className="text-xs font-semibold text-white uppercase tracking-wider">
              Synthetic Scenario Lab
            </h3>
          </div>
          <span className="text-[11px] text-slate-400">
            Image-to-Image reference preserving part geometry
          </span>
        </div>

        {/* Scenario Selection Cards */}
        <div>
          <label className="text-xs font-medium text-slate-300 mb-2 block">
            Select Degradation Scenario:
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
            {SCENARIOS.map(sc => {
              const isCompatible = sc.applicableModules.includes(module);
              const isSelected = selectedScenario === sc.id;
              const Icon = sc.icon;

              return (
                <div
                  key={sc.id}
                  onClick={() => {
                    if (isCompatible) setSelectedScenario(sc.id);
                  }}
                  className={`p-3 rounded-xl border transition-all select-none min-w-0 ${
                    !isCompatible
                      ? 'bg-white/[0.01] border-white/5 opacity-40 cursor-not-allowed'
                      : isSelected
                      ? 'bg-violet-950/40 border-violet-500/70 shadow-lg shadow-violet-950/20 cursor-pointer'
                      : 'bg-white/[0.02] border-white/10 hover:border-white/20 cursor-pointer'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <Icon size={16} className={isSelected ? 'text-violet-400' : 'text-slate-400'} />
                    {isSelected && (
                      <span className="w-2 h-2 rounded-full bg-violet-400 shadow-[0_0_8px_#8b5cf6]" />
                    )}
                    {!isCompatible && (
                      <Lock size={12} className="text-slate-500" />
                    )}
                  </div>
                  <h4 className="text-xs font-semibold text-slate-200 truncate">{sc.title}</h4>
                  <p className="text-[10px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                    {sc.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Parameters: Severity, Model, Variants */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 pt-2">
          {/* Severity Slider */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-slate-300">Severity:</span>
              <span className="font-mono text-violet-300 font-semibold">
                {SEVERITY_LABELS[severity]}
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={5}
              value={severity}
              onChange={e => setSeverity(Number(e.target.value))}
              className="w-full accent-violet-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-500 px-0.5">
              <span>Faint</span>
              <span>Moderate</span>
              <span>Severe</span>
            </div>
          </div>

          {/* Model Family Dropdown */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300 block">
              Generative Model Family:
            </label>
            <select
              value={selectedModel}
              onChange={e => setSelectedModel(e.target.value)}
              className="w-full bg-slate-900 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-violet-500"
            >
              {models.map(m => (
                <option key={m.id} value={m.id}>
                  {m.label} ({m.cost_hint})
                </option>
              ))}
            </select>
            <p className="text-[10px] text-slate-500">
              Populated from server allowlist ({models.length} families active)
            </p>
          </div>

          {/* Variants Selector */}
          <div className="space-y-1.5 min-w-0">
            <label className="text-xs font-medium text-slate-300 block">
              Output Variants (1 - 3):
            </label>
            <div className="flex items-center gap-1.5">
              {[1, 2, 3].map(v => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setVariantsCount(v)}
                  className={`flex-1 min-w-0 py-1.5 px-1 rounded-lg text-xs font-mono font-medium border text-center transition-all truncate ${
                    variantsCount === v
                      ? 'bg-violet-600/30 border-violet-500/60 text-violet-300'
                      : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
                  }`}
                >
                  {v} {v === 1 ? 'Variant' : 'Variants'}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-slate-500">
              Estimated: ~{variantsCount * 1.5} credit units
            </p>
          </div>
        </div>

        {/* User Note & Trigger Action */}
        <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
          <input
            type="text"
            placeholder="Optional context note (e.g. coastal atmosphere, 200°C chamber)..."
            value={userNote}
            maxLength={80}
            onChange={e => setUserNote(e.target.value)}
            className="flex-1 bg-slate-900/80 border border-white/10 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500"
          />
          <button
            onClick={handleTriggerSimulation}
            disabled={loading}
            className="w-full sm:w-auto px-5 py-2 rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-semibold flex items-center justify-center gap-2 shadow-lg shadow-violet-900/30 transition-all disabled:opacity-50"
          >
            {loading ? (
              <>
                <RefreshCw size={13} className="animate-spin" />
                Synthesizing Simulation…
              </>
            ) : (
              <>
                <Sparkles size={13} />
                Generate Simulation
              </>
            )}
          </button>
        </div>

        {error && (
          <p className="text-xs text-rose-400 flex items-center gap-1.5 pt-1">
            <AlertTriangle size={13} /> {error}
          </p>
        )}
      </div>

      {/* 3. Result Gallery & Interactive Compare Slider */}
      {activeSimulation && activeSimulation.variants?.length > 0 && (
        <div className="bg-white/[0.02] border border-white/10 rounded-2xl p-5 space-y-4 w-full overflow-hidden">
          {/* Header & Controls */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-white/10 pb-3">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-white uppercase tracking-wider">
                  Simulation Results
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-violet-900/40 text-violet-300 border border-violet-600/30 font-mono">
                  {activeSimulation.model_used || activeSimulation.model_requested}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-slate-400 font-mono">
                  {activeSimulation.prompt_version}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 italic">
                "{activeSimulation.prompt_text}"
              </p>
            </div>

            {/* View Mode Switcher */}
            <div className="flex items-center flex-wrap gap-1 bg-black/40 p-1 rounded-lg border border-white/10 shrink-0">
              <button
                onClick={() => setCompareMode('slider')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                  compareMode === 'slider' ? 'bg-violet-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
                }`}
              >
                <SplitSquareVertical size={12} className="inline mr-1" />
                Compare Slider
              </button>
              <button
                onClick={() => setCompareMode('sim_only')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                  compareMode === 'sim_only' ? 'bg-violet-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Sparkles size={12} className="inline mr-1" />
                Simulated View
              </button>
              <button
                onClick={() => setCompareMode('raw_only')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                  compareMode === 'raw_only' ? 'bg-violet-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Eye size={12} className="inline mr-1" />
                Original (Raw)
              </button>
            </div>
          </div>

          {/* Variant Selector Tabs if > 1 */}
          {activeSimulation.variants.length > 1 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Variant:</span>
              {activeSimulation.variants.map((v, i) => (
                <button
                  key={i}
                  onClick={() => setActiveVariantIdx(i)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium border transition-all ${
                    activeVariantIdx === i
                      ? 'bg-violet-600/30 border-violet-500/60 text-violet-300'
                      : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
                  }`}
                >
                  Variant {i + 1}
                </button>
              ))}
            </div>
          )}

          {/* Main Visualizer */}
          {currentVariant && (
            <div
              ref={containerRef}
              onMouseDown={handleMouseDown}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
              onMouseMove={handleMouseMove}
              onTouchStart={handleTouchStart}
              onTouchEnd={handleMouseUp}
              onTouchMove={handleTouchMove}
              className="relative select-none bg-black/60 border border-white/10 rounded-2xl overflow-hidden min-h-[380px] max-h-[560px] flex items-center justify-center cursor-ew-resize"
            >
              {/* Case 1: Raw Only */}
              {compareMode === 'raw_only' && (
                <div className="w-full h-full flex items-center justify-center">
                  <img src={rawImageUrl} alt="Original Part" className="max-h-[540px] w-auto object-contain" />
                  <span className="absolute top-4 left-4 bg-black/70 text-slate-300 text-xs px-2.5 py-1 rounded-md border border-white/10 font-mono">
                    Original Inspection Image
                  </span>
                </div>
              )}

              {/* Case 2: Simulated Only */}
              {compareMode === 'sim_only' && (
                <div className="w-full h-full flex items-center justify-center">
                  <img src={currentVariant.url} alt="Simulated Degradation" className="max-h-[540px] w-auto object-contain" />
                  <span className="absolute top-4 right-4 bg-purple-900/80 text-purple-200 text-xs px-2.5 py-1 rounded-md border border-purple-500/40 font-mono flex items-center gap-1.5">
                    <Sparkles size={11} className="text-purple-300" />
                    Simulated Degradation Variant
                  </span>
                </div>
              )}

              {/* Case 3: Interactive Slider Compare */}
              {compareMode === 'slider' && (
                <div className="relative w-full h-full min-h-[380px] flex items-center justify-center overflow-hidden">
                  {/* Underneath: Simulated image */}
                  <img
                    src={currentVariant.url}
                    alt="Simulated Degradation"
                    className="w-full h-full object-contain max-h-[540px] pointer-events-none"
                  />

                  {/* Overlaid clipped layer: Original Raw Image */}
                  <div
                    className="absolute inset-0 overflow-hidden pointer-events-none"
                    style={{ width: `${sliderPos}%` }}
                  >
                    <img
                      src={rawImageUrl}
                      alt="Original Inspection Part"
                      className="w-full h-full object-contain max-h-[540px]"
                      style={{
                        width: containerRef.current ? `${containerRef.current.clientWidth}px` : '100%',
                        maxWidth: 'none'
                      }}
                    />
                  </div>

                  {/* Split handle slider line */}
                  <div
                    className="absolute top-0 bottom-0 w-0.5 bg-violet-400 shadow-[0_0_12px_rgba(167,139,250,0.8)] pointer-events-none"
                    style={{ left: `${sliderPos}%` }}
                  >
                    <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-violet-600 border-2 border-white flex items-center justify-center shadow-xl">
                      <Sliders size={13} className="text-white rotate-90" />
                    </div>
                  </div>

                  {/* Badges on left and right */}
                  <div className="absolute top-4 left-4 pointer-events-none bg-black/75 text-slate-300 text-xs px-2.5 py-1 rounded-md border border-white/10 font-mono">
                    Original Part
                  </div>
                  <div className="absolute top-4 right-4 pointer-events-none bg-purple-950/80 text-purple-200 text-xs px-2.5 py-1 rounded-md border border-purple-500/40 font-mono flex items-center gap-1.5">
                    <Sparkles size={11} className="text-purple-300" />
                    Simulated: {currentVariant.scenario}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Fidelity Metric & Verification Info */}
          {currentVariant && (
            <div className="flex items-center justify-between text-xs text-slate-400 bg-black/30 p-3 rounded-xl border border-white/5">
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-300">Geometry Preservation (Edge SSIM):</span>
                <span className="font-mono text-emerald-400 font-bold">
                  {(currentVariant.edge_fidelity_ssim * 100).toFixed(1)}%
                </span>
                <span className="text-[10px] text-slate-500">
                  (Canny edge alignment against original reference)
                </span>
              </div>
              <span className="text-[10px] text-purple-300 font-mono">
                Tagged: parent:{jobId}, feature:simulation
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
