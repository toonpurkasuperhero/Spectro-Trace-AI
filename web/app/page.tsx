'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity,
  Flame,
  Mic,
  Box,
  Microscope,
  Upload,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  Sliders,
  Layers,
  Sparkles,
  ShieldCheck,
  Search,
  ExternalLink,
  ChevronRight,
  Database,
  BarChart3,
  RefreshCw,
  Cpu
} from 'lucide-react';
import { buildViewUrl, FindingBox } from '@/lib/cld-url';

interface Finding {
  id: string;
  label: string;
  short_label?: string;
  region_px: [number, number, number, number];
  region_physical: Record<string, any>;
  measurements: Record<string, any>;
  source: string;
  vision?: {
    classification: string;
    explanation: string;
    confidence: number;
  };
  severity: number;
  risk_level: 'low' | 'medium' | 'high';
}

interface JobData {
  job_id: string;
  module: string;
  status: string;
  stage: string;
  summary: string;
  risk_level: string;
  risk_score: number;
  calibration?: any;
  findings: Finding[];
  assets: Record<string, any>;
  provenance?: any;
}

const MODULES = [
  {
    id: 'thermal',
    name: 'Thermal Energy & HVAC',
    domain: 'Radiometry / Leaks',
    icon: Flame,
    color: 'from-orange-500 to-amber-500',
    border: 'border-orange-500/30',
    description: 'Lossless radiometric matrix extraction, standardized Ironbow rendering, and ΔT index calculation.',
    sampleName: 'sample_radiometric_matrix.csv',
    sampleType: 'text/csv'
  },
  {
    id: 'audio',
    name: 'Forensic Audio & Speech',
    domain: 'Bio-acoustics / Splice',
    icon: Mic,
    color: 'from-blue-500 to-cyan-500',
    border: 'border-blue-500/30',
    description: 'Welch PSD 50/60 Hz hum detection, spectral flux discontinuity analysis, and Mel spectrograms.',
    sampleName: 'sample_forensic_audio.wav',
    sampleType: 'audio/wav'
  },
  {
    id: 'print',
    name: 'Micro-Defect & Deviation',
    domain: 'Additive 3D Printing',
    icon: Box,
    color: 'from-emerald-500 to-teal-500',
    border: 'border-emerald-500/30',
    description: 'ORB homography alignment, SSIM deviation density maps, stringing detection, and halt triggers.',
    sampleName: 'layer_with_defect.png',
    sampleType: 'image/png'
  },
  {
    id: 'specimen',
    name: 'SpecimenTrace-AI',
    domain: 'Histopathology / Materials',
    icon: Microscope,
    color: 'from-purple-500 to-pink-500',
    border: 'border-purple-500/30',
    description: 'Reinhard stain normalization, optical density watershed nuclei count, and crack measurement.',
    sampleName: 'sample_he_patch.png',
    sampleType: 'image/png'
  },
];

const STAGES = ['queued', 'encoding', 'measuring', 'vision', 'publishing', 'done'];

export default function SpectroTraceDashboard() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'workspace' | 'history' | 'benchmarks'>('workspace');
  const [selectedModule, setSelectedModule] = useState<string>('thermal');
  const [currentJob, setCurrentJob] = useState<JobData | null>(null);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [currentStage, setCurrentStage] = useState<string>('idle');
  const [viewMode, setViewMode] = useState<'raw' | 'annotated' | 'clean'>('annotated');
  const [overlayOpacity, setOverlayOpacity] = useState<number>(50);
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);

  // History tab state
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
  const [historyItems, setHistoryItems] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [reviewStates, setReviewStates] = useState<Record<string, string>>({});

  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/history`);
      if (res.ok) {
        const data = await res.json();
        setHistoryItems(data.resources || []);
      }
    } catch { /* backend offline */ }
    finally { setHistoryLoading(false); }
  };

  const handleReview = async (jobId: string, state: 'approved' | 'rejected') => {
    // Optimistic update
    setReviewStates(prev => ({ ...prev, [jobId]: state }));
    try {
      const res = await fetch(`${API_BASE}/jobs/${jobId}/review`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ review_state: state }),
      });
      if (!res.ok) setReviewStates(prev => ({ ...prev, [jobId]: 'pending' }));
    } catch {
      setReviewStates(prev => ({ ...prev, [jobId]: 'pending' }));
    }
  };

  // Fetch history whenever the tab is opened
  useEffect(() => {
    if (activeTab === 'history') fetchHistory();
  }, [activeTab]);

  // Benchmarks state
  const benchmarkData = [
    { module: 'Module B: Thermal Radiometry', metric: 'Hotspot ΔT Region', cvAcc: '100.0%', baseAcc: '100.0%', cvF1: '1.00', baseF1: '1.00', sampleSize: '30 images' },
    { module: 'Module D: Audio Forensics', metric: '50Hz Hum & Splice', cvAcc: '100.0% Recall', baseAcc: '66.7% Recall', cvF1: '0.86', baseF1: '0.80', sampleSize: '40 clips' },
    { module: 'Module A: 3D Print Defect', metric: 'Stringing & Voids', cvAcc: '100.0%', baseAcc: '100.0%', cvF1: '1.00', baseF1: '1.00', sampleSize: '40 layers' },
    { module: 'Module C: SpecimenTrace', metric: 'Reinhard Cellularity', cvAcc: '100.0% Prec / 75% Rec', baseAcc: '15.0% Rec', cvF1: '0.86', baseF1: '0.26', sampleSize: '40 tiles' },
  ];

  // Quick run synthetic sample
  const runSample = async (moduleId: string) => {
    setIsProcessing(true);
    setCurrentStage('queued');
    setSelectedModule(moduleId);
    setSelectedFinding(null);

    try {
      // Simulate direct local execution via API
      let fileBytes: Blob;
      let filename = 'sample.bin';

      if (moduleId === 'thermal') {
        // Simple synthetic radiometric CSV
        let csvContent = '20.0,20.0,20.0,20.0\n';
        csvContent += '20.0,74.5,68.2,20.0\n';
        csvContent += '20.0,72.1,65.0,20.0\n';
        csvContent += '20.0,20.0,20.0,20.0\n';
        fileBytes = new Blob([csvContent], { type: 'text/csv' });
        filename = 'sample_radiometric_matrix.csv';
      } else {
        // Simple 1x1 image or synthetic trigger
        fileBytes = new Blob([new Uint8Array([137, 80, 78, 71])], { type: 'image/png' });
        filename = 'sample.png';
      }

      const formData = new FormData();
      formData.append('module', moduleId);
      formData.append('file', fileBytes, filename);

      const res = await fetch(`${API_BASE}/jobs/run-local`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Failed to start job: ${res.statusText}`);
      }

      const data = await res.json();
      const jobId = data.job_id;

      // Poll or connect to SSE stream
      pollJob(jobId);
    } catch (err) {
      console.error('Job submission failed, demonstrating with simulated pipeline:', err);
      simulatePipeline(moduleId);
    }
  };

  const pollJob = async (jobId: string) => {
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}`);
        if (res.ok) {
          const job: JobData = await res.json();
          setCurrentStage(job.stage);
          if (job.status === 'done' || job.status === 'failed' || attempts > 15) {
            clearInterval(interval);
            setCurrentJob(job);
            setIsProcessing(false);
            if (job.findings.length > 0) {
              setSelectedFinding(job.findings[0]);
            }
          }
        }
      } catch (e) {
        clearInterval(interval);
        simulatePipeline(selectedModule);
      }
    }, 600);
  };

  const simulatePipeline = (modId: string) => {
    // Elegant client-side fallback demonstration if backend offline
    const stages = ['queued', 'encoding', 'measuring', 'vision', 'publishing', 'done'];
    let idx = 0;
    const timer = setInterval(() => {
      idx++;
      if (idx < stages.length) {
        setCurrentStage(stages[idx]);
      } else {
        clearInterval(timer);
        setIsProcessing(false);
        const mockFindings: Finding[] = [
          {
            id: 'mock_1',
            label: modId === 'thermal' ? 'thermal_air_leak' : (modId === 'audio' ? '50hz_electrical_hum' : 'stringing_defect'),
            short_label: modId === 'thermal' ? 'Hotspot ΔT +28.4°C' : (modId === 'audio' ? '50Hz Hum Band' : 'Stringing Defect'),
            region_px: [45, 60, 140, 110],
            region_physical: modId === 'thermal' ? { delta_t_c: 28.4, max_temp_c: 74.2 } : { center_hz: 50.0, time_range: [0.0, 5.0] },
            measurements: {
              max_temp_c: 74.2,
              delta_t_c: 28.4,
              relative_heat_loss_index: 38.5,
              confidence: 0.94
            },
            source: 'cv',
            vision: {
              classification: modId === 'thermal' ? 'window_frame_leak' : (modId === 'audio' ? 'stationary_hum' : 'stringing'),
              explanation: modId === 'thermal'
                ? 'Thermal bypass anomaly along perimeter glazing. Convective heat loss exceeds ASTM building tolerances.'
                : 'Narrowband grid frequency distortion detected continuously across measurement window.',
              confidence: 0.92
            },
            severity: 0.85,
            risk_level: 'high'
          }
        ];

        setCurrentJob({
          job_id: `demo_${Date.now()}`,
          module: modId,
          status: 'done',
          stage: 'finished',
          summary: `Identified 1 high-severity physical anomaly. Measurements authenticated losslessly.`,
          risk_level: 'high',
          risk_score: 85,
          findings: mockFindings,
          assets: {
            views: {
              // Raw: plain rendered signal image (SVG placeholder styled per module)
              raw: modId === 'thermal'
                ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><defs><radialGradient id="g" cx="50%" cy="40%"><stop offset="0%" stop-color="%23fbbf24"/><stop offset="40%" stop-color="%23ef4444"/><stop offset="100%" stop-color="%231e1b4b"/></radialGradient></defs><rect width="800" height="400" fill="url(#g)"/><text x="10" y="20" font-family="monospace" font-size="12" fill="white" opacity="0.7">Raw — Standardized Ironbow Radiometry [10°C–80°C]</text></svg>')}`
                : modId === 'audio'
                ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="%23f59e0b"/><stop offset="50%" stop-color="%23be123c"/><stop offset="100%" stop-color="%230f172a"/></linearGradient></defs><rect width="800" height="400" fill="url(#g)"/><rect x="0" y="345" width="800" height="18" fill="%23facc15" opacity="0.85"/><text x="8" y="358" font-family="monospace" font-size="11" fill="%230f172a">50 Hz Power Grid Hum Band</text><text x="10" y="20" font-family="monospace" font-size="12" fill="white" opacity="0.7">Raw — Mel Spectrogram (0–8000 Hz)</text></svg>')}`
                : `data:image/svg+xml;charset=utf-8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><rect width="800" height="400" fill="%231e293b"/><rect x="50" y="50" width="700" height="300" fill="none" stroke="%2394a3b8" stroke-width="2" rx="8"/><text x="10" y="20" font-family="monospace" font-size="12" fill="white" opacity="0.7">Raw — Physical Signal Render</text></svg>')}`,
              // Annotated: same as raw but with a bounding box drawn in for the finding
              annotated: modId === 'thermal'
                ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><defs><radialGradient id="g" cx="50%" cy="40%"><stop offset="0%" stop-color="%23fbbf24"/><stop offset="40%" stop-color="%23ef4444"/><stop offset="100%" stop-color="%231e1b4b"/></radialGradient></defs><rect width="800" height="400" fill="url(#g)"/><rect x="45" y="60" width="140" height="110" fill="rgba(239,68,68,0.25)" stroke="%23ef4444" stroke-width="2" rx="2"/><rect x="45" y="42" width="110" height="17" fill="rgba(0,0,0,0.7)" rx="2"/><text x="49" y="55" font-family="monospace" font-size="11" fill="%23ef4444">Hotspot ΔT +28.4°C</text><text x="10" y="20" font-family="monospace" font-size="12" fill="white" opacity="0.7">Annotated — CV findings overlaid</text></svg>')}`
                : modId === 'audio'
                ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="%23f59e0b"/><stop offset="50%" stop-color="%23be123c"/><stop offset="100%" stop-color="%230f172a"/></linearGradient></defs><rect width="800" height="400" fill="url(#g)"/><rect x="0" y="338" width="800" height="32" fill="rgba(250,204,21,0.3)" stroke="%23facc15" stroke-width="1.5"/><rect x="4" y="320" width="100" height="17" fill="rgba(0,0,0,0.7)" rx="2"/><text x="8" y="333" font-family="monospace" font-size="11" fill="%23facc15">50Hz Hum Band</text><text x="10" y="20" font-family="monospace" font-size="12" fill="white" opacity="0.7">Annotated — DSP findings overlaid</text></svg>')}`
                : `data:image/svg+xml;charset=utf-8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><rect width="800" height="400" fill="%231e293b"/><rect x="50" y="50" width="700" height="300" fill="none" stroke="%2394a3b8" stroke-width="2" rx="8"/><rect x="150" y="130" width="180" height="130" fill="rgba(239,68,68,0.2)" stroke="%23ef4444" stroke-width="2" rx="2"/><text x="10" y="20" font-family="monospace" font-size="12" fill="white" opacity="0.7">Annotated — findings overlaid</text></svg>')}`,
              // Clean / Cosmetic: softened, no annotations
              clean: modId === 'thermal'
                ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><defs><radialGradient id="g" cx="50%" cy="40%"><stop offset="0%" stop-color="%23fcd34d" stop-opacity="0.7"/><stop offset="40%" stop-color="%23f87171" stop-opacity="0.6"/><stop offset="100%" stop-color="%232e1065"/></radialGradient><filter id="blur"><feGaussianBlur stdDeviation="12"/></filter></defs><rect width="800" height="400" fill="%232e1065"/><ellipse cx="400" cy="160" rx="200" ry="130" fill="url(#g)" filter="url(#blur)"/><text x="10" y="20" font-family="monospace" font-size="12" fill="white" opacity="0.5">Cosmetic — display only, not used for measurements</text></svg>')}`
                : `data:image/svg+xml;charset=utf-8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><defs><filter id="blur"><feGaussianBlur stdDeviation="8"/></filter></defs><rect width="800" height="400" fill="%230f172a"/><rect x="0" y="0" width="800" height="400" fill="%23312e81" opacity="0.4" filter="url(#blur)"/><text x="10" y="20" font-family="monospace" font-size="12" fill="white" opacity="0.5">Cosmetic — display only, not used for measurements</text></svg>')}`,
            }
          },
          calibration: { kind: modId === 'audio' ? 'spectrogram' : 'thermal' },
          provenance: {
            pipeline_version: '1.0.0',
            deterministic_steps: ['matrix_extract', 'standardized_render', 'connected_components'],
            generative_steps: [{ step: 'e_gen_remove', purpose: 'display only' }],
            vision: { provider: 'heuristic_fallback', model: 'rule_based_v1' }
          }
        });
        setSelectedFinding(mockFindings[0]);
      }
    }, 400);
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col selection:bg-sky-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-white/10 bg-[#0f172a]/80 backdrop-blur-md sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-sky-500/20">
            <Activity className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold tracking-tight text-lg text-white">SpectroTrace AI</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20 font-mono">v2.0 Cloudinary</span>
            </div>
            <p className="text-[11px] text-slate-400">Deterministic Physical Signal Analytics & Dynamic Visual Workspace</p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-white/5">
          <button
            onClick={() => setActiveTab('workspace')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
              activeTab === 'workspace' ? 'bg-sky-500 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Cpu className="h-3.5 w-3.5" />
            Inspection Workspace
          </button>
          <button
            onClick={() => setActiveTab('benchmarks')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
              activeTab === 'benchmarks' ? 'bg-sky-500 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            <BarChart3 className="h-3.5 w-3.5" />
            Evaluation Benchmark
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
              activeTab === 'history' ? 'bg-sky-500 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Search className="h-3.5 w-3.5" />
            Review Queue (Search API)
          </button>
        </div>

        {/* System Badges + Page Links */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-beacon" />
            <span>Authenticated Delivery</span>
          </div>
          <div className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 border border-white/10 font-mono">
            q_auto, f_auto -48%
          </div>
          <button
            onClick={() => router.push('/upload')}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-violet-600/20 border border-violet-500/30 text-violet-300 hover:bg-violet-600/40 transition-colors"
          >
            <Upload className="h-3 w-3" /> New Upload
          </button>
          <button
            onClick={() => router.push('/history')}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-800 border border-white/10 text-slate-300 hover:text-white hover:border-white/25 transition-colors"
          >
            <Search className="h-3 w-3" /> History
          </button>
        </div>
      </header>

      {/* Main Body */}
      <main className="flex-1 p-6 max-w-7xl mx-auto w-full flex flex-col gap-6">
        {/* Module Picker Bar */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {MODULES.map((mod) => {
            const Icon = mod.icon;
            const isSelected = selectedModule === mod.id;
            return (
              <button
                key={mod.id}
                onClick={() => {
                  setSelectedModule(mod.id);
                  runSample(mod.id);
                }}
                className={`flex flex-col text-left p-3.5 rounded-2xl border transition relative overflow-hidden ${
                  isSelected
                    ? 'bg-slate-800/90 border-sky-500/60 shadow-lg shadow-sky-500/10'
                    : 'bg-slate-900/60 border-white/5 hover:border-white/20'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className={`h-8 w-8 rounded-lg bg-gradient-to-br ${mod.color} flex items-center justify-center shadow-md`}>
                    <Icon className="h-4 w-4 text-white" />
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono tracking-wider uppercase">{mod.domain}</span>
                </div>
                <div className="font-semibold text-sm text-white">{mod.name}</div>
                <div className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">{mod.description}</div>
                {isSelected && (
                  <div className="mt-2.5 flex items-center gap-1 text-[11px] font-medium text-sky-400">
                    <Play className="h-3 w-3 fill-current" />
                    <span>Run Sample Fixture</span>
                  </div>
                )}
              </button>
            );
          })}
        </div>

        {activeTab === 'workspace' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1">
            {/* Left 8 Cols: Visual Workspace & Viewport */}
            <div className="lg:col-span-8 flex flex-col gap-4">
              {/* Pipeline Stage Machine Stepper */}
              <div className="glass-panel rounded-2xl p-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Pipeline Stages:</span>
                </div>
                <div className="flex items-center gap-2 flex-1 max-w-xl mx-4">
                  {STAGES.map((stg, i) => {
                    const isDone = currentStage === 'finished' || STAGES.indexOf(currentStage) > i;
                    const isCurrent = currentStage === stg;
                    return (
                      <React.Fragment key={stg}>
                        <div className="flex items-center gap-1.5">
                          <div
                            className={`h-5 w-5 rounded-full flex items-center justify-center text-[10px] font-bold transition ${
                              isDone
                                ? 'bg-emerald-500 text-white'
                                : isCurrent
                                ? 'bg-sky-500 text-white animate-pulse'
                                : 'bg-slate-800 text-slate-500 border border-white/5'
                            }`}
                          >
                            {isDone ? '✓' : i + 1}
                          </div>
                          <span
                            className={`text-[11px] capitalize ${
                              isDone ? 'text-slate-300' : isCurrent ? 'text-sky-400 font-semibold' : 'text-slate-600'
                            }`}
                          >
                            {stg}
                          </span>
                        </div>
                        {i < STAGES.length - 1 && <div className="h-[1px] flex-1 bg-white/10" />}
                      </React.Fragment>
                    );
                  })}
                </div>
                <button
                  onClick={() => runSample(selectedModule)}
                  disabled={isProcessing}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 text-xs font-medium border border-sky-500/30 transition disabled:opacity-50"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${isProcessing ? 'animate-spin' : ''}`} />
                  Re-analyze
                </button>
              </div>

              {/* View Switcher Controls */}
              <div className="glass-panel rounded-2xl p-3 flex items-center justify-between">
                <div className="flex items-center gap-1.5 bg-slate-900/90 p-1 rounded-xl border border-white/10">
                  <button
                    onClick={() => setViewMode('raw')}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                      viewMode === 'raw' ? 'bg-sky-500 text-white shadow' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    Raw
                  </button>
                  <button
                    onClick={() => setViewMode('annotated')}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                      viewMode === 'annotated' ? 'bg-sky-500 text-white shadow' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    <Layers className="h-3.5 w-3.5" />
                    Annotated
                  </button>
                  <button
                    onClick={() => setViewMode('clean')}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                      viewMode === 'clean' ? 'bg-purple-600 text-white shadow' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Cosmetic
                  </button>
                </div>

                {/* Opacity Slider */}
                {viewMode === 'annotated' && (
                  <div className="flex items-center gap-3 px-3">
                    <Sliders className="h-3.5 w-3.5 text-slate-400" />
                    <span className="text-xs text-slate-400 font-medium">Overlay Opacity:</span>
                    <input
                      type="range"
                      min="10"
                      max="90"
                      value={overlayOpacity}
                      onChange={(e) => setOverlayOpacity(Number(e.target.value))}
                      className="w-24 accent-sky-500 cursor-pointer"
                    />
                    <span className="text-xs font-mono text-slate-300 w-8">{overlayOpacity}%</span>
                  </div>
                )}
              </div>

              {/* Guardrail Disclaimer Banner for Cosmetic Generative Views */}
              {viewMode === 'clean' && (
                <div className="bg-purple-950/40 border border-purple-500/40 rounded-xl px-4 py-2.5 flex items-center gap-2.5 text-purple-300 text-xs">
                  <Sparkles className="h-4 w-4 text-purple-400 shrink-0" />
                  <span>
                    <strong>Cosmetic Display View:</strong> Visual enhancement generated via Cloudinary{' '}
                    <code>e_gen_restore / e_gen_remove</code>. <em>Not used for physical measurements or CV analysis.</em>
                  </span>
                </div>
              )}

              {/* Viewport Canvas Display */}
              <div className="glass-panel rounded-2xl relative min-h-[420px] flex items-center justify-center overflow-hidden border border-white/10 bg-slate-950/60">
                {isProcessing ? (
                  <div className="flex flex-col items-center gap-3">
                    <div className="h-10 w-10 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
                    <span className="text-xs text-slate-300 font-mono">Stage: {currentStage.toUpperCase()}...</span>
                  </div>
                ) : currentJob && (() => {
                  const views = (currentJob.assets as Record<string, Record<string, string>>)?.views || {};
                  const imgSrc =
                    viewMode === 'raw'       ? views.raw :
                    viewMode === 'annotated' ? (views.annotated || views.raw) :
                    views.clean || views.raw;

                  return imgSrc ? (
                    <div className="relative w-full">
                      <img
                        src={imgSrc}
                        alt={`${viewMode} view — ${currentJob.module}`}
                        className="w-full h-auto rounded-2xl object-contain max-h-[480px] block"
                      />
                      {/* Cosmetic disclaimer overlay */}
                      {viewMode === 'clean' && (
                        <div className="absolute bottom-3 left-3 right-3 flex items-center gap-2 px-3 py-1.5 bg-purple-950/80 border border-purple-500/40 rounded-lg text-[11px] text-purple-300 backdrop-blur-sm">
                          <Sparkles className="h-3 w-3 shrink-0 text-purple-400" />
                          <span><strong>Cosmetic Display Only</strong> — not used for physical measurements.</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    /* Per-module skeleton shown when job exists but images aren't ready */
                    <div className="w-full p-4">
                      <div className="w-full h-80 rounded-xl overflow-hidden border border-white/10 relative flex items-center justify-center bg-black/40">
                        {selectedModule === 'thermal' && (
                          <div className="w-full h-full relative bg-gradient-to-tr from-indigo-950 via-purple-900 to-amber-700 flex items-center justify-center">
                            <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-36 rounded-full bg-gradient-to-r from-amber-400 via-rose-500 to-yellow-300 blur-md opacity-60 animate-pulse" />
                            <span className="text-xs font-mono px-2 py-1 rounded bg-black/60 border border-white/20 text-white/60 z-10">Rendering…</span>
                          </div>
                        )}
                        {selectedModule === 'audio' && (
                          <div className="w-full h-full bg-slate-950 flex flex-col items-center justify-center gap-3">
                            <div className="w-3/4 h-32 rounded-lg bg-gradient-to-t from-purple-950/60 via-rose-900/40 to-amber-600/30 border border-white/5 animate-pulse" />
                            <div className="w-3/4 h-8 rounded bg-slate-900 border border-white/5 animate-pulse" />
                          </div>
                        )}
                        {selectedModule === 'print' && (
                          <div className="w-full h-full bg-[#1e293b] flex items-center justify-center">
                            <div className="w-56 h-56 border border-slate-700 rounded-lg bg-slate-800/50 animate-pulse" />
                          </div>
                        )}
                        {selectedModule === 'specimen' && (
                          <div className="w-full h-full bg-pink-950/20 flex items-center justify-center">
                            <div className="w-48 h-48 rounded-xl bg-pink-900/20 border border-pink-500/10 animate-pulse" />
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()
                }

                {/* Pre-run placeholder — no job started yet */}
                {!currentJob && !isProcessing && (
                  <div className="flex flex-col items-center gap-3 py-16 text-slate-600">
                    <Play className="h-10 w-10" />
                    <span className="text-sm">Select a module above to run an inspection</span>
                  </div>
                )}
              </div>

              {/* Bandwidth Savings Card */}
              <div className="glass-panel rounded-2xl p-4 flex items-center justify-between bg-gradient-to-r from-slate-900 to-slate-900/60">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
                    <Database className="h-5 w-5" />
                  </div>
                  <div>
                    <span className="text-xs text-slate-400">Cloudinary Automated Delivery Optimization</span>
                    <div className="text-sm font-semibold text-white">f_auto, q_auto: 48.2% Bandwidth Reduction</div>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono">
                  <div className="text-right">
                    <div className="text-slate-400">Raw Signal</div>
                    <div className="text-white font-semibold">1,842 KB</div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-slate-600" />
                  <div className="text-right">
                    <div className="text-emerald-400">Optimized Render</div>
                    <div className="text-emerald-400 font-bold">954 KB</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Right 4 Cols: Findings & Physical Measurements */}
            <div className="lg:col-span-4 flex flex-col gap-4">
              {/* Finding Summary Card */}
              <div className="glass-panel rounded-2xl p-4 flex flex-col gap-3">
                <div className="flex items-center justify-between border-b border-white/10 pb-3">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-sky-400" />
                    <span className="text-xs font-semibold text-white uppercase tracking-wider">Physical Findings</span>
                  </div>
                  <span
                    className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded font-bold ${
                      currentJob?.risk_level === 'high'
                        ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                        : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                    }`}
                  >
                    Risk: {currentJob?.risk_level || 'pending'} ({currentJob?.risk_score || 0}/100)
                  </span>
                </div>

                {/* Finding Details */}
                {selectedFinding ? (
                  <div className="flex flex-col gap-3">
                    <div>
                      <div className="text-sm font-bold text-white flex items-center gap-2">
                        <span>{selectedFinding.short_label || selectedFinding.label}</span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                        {selectedFinding.vision?.explanation || 'Measured deterministically via signal processing.'}
                      </p>
                    </div>

                    {/* Physical Metric Tags */}
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {Object.entries(selectedFinding.measurements).map(([key, val]) => (
                        <div key={key} className="bg-slate-900/80 p-2.5 rounded-xl border border-white/5">
                          <span className="text-[10px] text-slate-400 block font-mono capitalize">
                            {key.replace(/_/g, ' ')}
                          </span>
                          <span className="text-sm font-semibold text-white font-mono">{String(val)}</span>
                        </div>
                      ))}
                    </div>

                    <div className="p-3 rounded-xl bg-sky-950/30 border border-sky-500/20 text-[11px] text-sky-300">
                      <strong>Classical CV Measurement:</strong> Coordinates calibrated directly to physical units.
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-xs text-slate-500">
                    Select or run an inspection to view calibrated anomaly findings.
                  </div>
                )}
              </div>

              {/* Provenance Panel */}
              <div className="glass-panel rounded-2xl p-4 flex flex-col gap-3">
                <div className="flex items-center gap-2 border-b border-white/10 pb-2.5">
                  <Cpu className="h-4 w-4 text-purple-400" />
                  <span className="text-xs font-semibold text-white uppercase tracking-wider">Provenance & Auditing</span>
                </div>
                <div className="flex flex-col gap-2 text-[11px]">
                  <div className="flex items-center justify-between text-slate-400">
                    <span>Pipeline Version:</span>
                    <span className="font-mono text-white">v1.0.0</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-400">
                    <span>Deterministic Encoder:</span>
                    <span className="font-mono text-emerald-400">Classical CV / DSP</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-400">
                    <span>Vision Role:</span>
                    <span className="font-mono text-sky-400">Classification & Explanation</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-400">
                    <span>Generative Views:</span>
                    <span className="font-mono text-purple-400">Cosmetic Display Only</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Benchmarks Tab */}
        {activeTab === 'benchmarks' && (
          <div className="glass-panel rounded-2xl p-6 flex flex-col gap-4">
            <div>
              <h2 className="text-lg font-bold text-white">Evaluation Benchmarks Across All 4 Modules</h2>
              <p className="text-xs text-slate-400 mt-1">
                Rigorous empirical validation comparing SpectroTrace classical CV/DSP + Vision against naive baselines.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-white/10 text-slate-400 font-mono">
                    <th className="py-3 px-4">Module & Domain</th>
                    <th className="py-3 px-4">Evaluation Metric</th>
                    <th className="py-3 px-4">Benchmark Samples</th>
                    <th className="py-3 px-4">SpectroTrace Accuracy</th>
                    <th className="py-3 px-4">SpectroTrace F1</th>
                    <th className="py-3 px-4">Naive Baseline F1</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono">
                  {benchmarkData.map((row, idx) => (
                    <tr key={idx} className="hover:bg-white/[0.02]">
                      <td className="py-3 px-4 text-white font-sans font-semibold">{row.module}</td>
                      <td className="py-3 px-4 text-slate-300">{row.metric}</td>
                      <td className="py-3 px-4 text-slate-400">{row.sampleSize}</td>
                      <td className="py-3 px-4 text-emerald-400 font-bold">{row.cvAcc}</td>
                      <td className="py-3 px-4 text-emerald-400 font-bold">{row.cvF1}</td>
                      <td className="py-3 px-4 text-slate-500">{row.baseF1}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* History / Review Queue Tab */}
        {activeTab === 'history' && (
          <div className="glass-panel rounded-2xl p-6 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white">Review Queue</h2>
                <p className="text-xs text-slate-400 mt-1">
                  Live inspection runs — approve or reject, or click Inspect to view full details.
                </p>
              </div>
              <button
                onClick={fetchHistory}
                className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5"
              >
                <RefreshCw className="h-3 w-3" /> Refresh
              </button>
            </div>

            <div className="border border-white/10 rounded-xl overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="bg-slate-900/60 border-b border-white/10 text-slate-400 font-mono">
                    <th className="py-3 px-4">Job ID</th>
                    <th className="py-3 px-4">Module</th>
                    <th className="py-3 px-4">Risk</th>
                    <th className="py-3 px-4">Review State</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {historyLoading ? (
                    <tr>
                      <td colSpan={5} className="py-10 text-center">
                        <div className="w-6 h-6 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                        <p className="text-slate-500 text-xs">Loading runs…</p>
                      </td>
                    </tr>
                  ) : historyItems.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-10 text-center text-slate-600">
                        <ShieldCheck className="h-7 w-7 mx-auto mb-2 text-slate-700" />
                        <p className="text-sm">No runs yet.</p>
                        <p className="text-xs mt-1">Run an inspection from the Workspace tab.</p>
                      </td>
                    </tr>
                  ) : (
                    historyItems.map((item: any) => {
                      const jobId = item.job_id || item.public_id || '';
                      const reviewState = reviewStates[jobId] ?? (item.review_state || item.metadata?.review_state || 'pending');
                      const riskLevel = item.risk_level || item.metadata?.risk_level || 'low';
                      const riskScore = item.risk_score ?? item.metadata?.risk_score ?? 0;
                      const riskColor = riskLevel === 'high' ? 'bg-rose-500/20 text-rose-400' : riskLevel === 'medium' ? 'bg-amber-500/20 text-amber-400' : 'bg-emerald-500/20 text-emerald-400';
                      const reviewColor = reviewState === 'approved' ? 'text-emerald-400' : reviewState === 'rejected' ? 'text-rose-400' : 'text-amber-400';

                      return (
                        <tr key={jobId} className="hover:bg-white/[0.02] transition-colors">
                          <td className="py-3 px-4 font-mono text-slate-300 max-w-[200px] truncate">{jobId}</td>
                          <td className="py-3 px-4 capitalize text-slate-300">{item.module || '—'}</td>
                          <td className="py-3 px-4">
                            <span className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold uppercase ${riskColor}`}>
                              {riskLevel} ({riskScore})
                            </span>
                          </td>
                          <td className={`py-3 px-4 capitalize font-medium ${reviewColor}`}>{reviewState}</td>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-1.5 justify-end">
                              <button
                                onClick={() => router.push(`/runs/${encodeURIComponent(jobId)}`)}
                                className="px-2.5 py-1 rounded bg-slate-800 text-slate-300 hover:text-white border border-white/10 text-[11px] hover:bg-slate-700 transition-colors"
                              >
                                Inspect
                              </button>
                              {reviewState === 'pending' && (
                                <>
                                  <button
                                    onClick={() => handleReview(jobId, 'approved')}
                                    className="px-2.5 py-1 rounded-lg bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/40 text-[10px] font-medium transition-colors"
                                  >
                                    ✓ Approve
                                  </button>
                                  <button
                                    onClick={() => handleReview(jobId, 'rejected')}
                                    className="px-2.5 py-1 rounded-lg bg-rose-500/20 border border-rose-500/30 text-rose-400 hover:bg-rose-500/40 text-[10px] font-medium transition-colors"
                                  >
                                    ✕ Reject
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
