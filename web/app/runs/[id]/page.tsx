'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, CheckCircle2, AlertTriangle, Clock, Cpu, Layers, Eye,
  EyeOff, Sliders, ChevronRight, Play, Pause, Volume2, ZoomIn,
  ShieldCheck, Info, AlertCircle, RefreshCw, ExternalLink, BarChart3,
  Activity, Thermometer, Mic, Box, Microscope, Download
} from 'lucide-react';
import ExportMenu from '@/components/ExportMenu';
import ViewTabs, { ViewMode } from '@/components/ViewTabs';
import RemediationView from '@/components/RemediationView';
import SimulationPanel from '@/components/SimulationPanel';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
const CLD_CLOUD = process.env.NEXT_PUBLIC_CLD_CLOUD_NAME || '';

// ── Types ─────────────────────────────────────────────────────────────────────
interface Finding {
  id: string;
  label: string;
  short_label?: string;
  region_px: [number, number, number, number];
  region_physical: Record<string, unknown>;
  measurements: Record<string, unknown>;
  source: string;
  vision?: { classification: string; explanation: string; confidence: number };
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
  error?: string;
  calibration?: Record<string, unknown>;
  findings: Finding[];
  assets: Record<string, unknown>;
  provenance?: {
    pipeline_version: string;
    deterministic_steps: string[];
    generative_steps: { step: string; purpose: string }[];
    vision?: { provider: string; model: string; prompt_version: string };
    input_hash?: string;
  };
}

// ── Stage stepper ─────────────────────────────────────────────────────────────
const STAGES = ['queued', 'encoding', 'measuring', 'vision', 'publishing', 'finished'];

const STAGE_LABELS: Record<string, string> = {
  queued: 'Queued',
  encoding: 'Encoding',
  measuring: 'Measuring',
  vision: 'Vision AI',
  publishing: 'Publishing',
  finished: 'Complete',
};

function StageStepper({ stage, status }: { stage: string; status: string }) {
  const currentIdx = STAGES.indexOf(stage);
  const isFailed = status === 'failed';

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {STAGES.map((s, i) => {
        const done = i < currentIdx || (s === 'finished' && status.startsWith('done'));
        const active = i === currentIdx && !isFailed;
        const failed = isFailed && i === currentIdx;
        return (
          <React.Fragment key={s}>
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
              done    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' :
              active  ? 'bg-violet-500/20 text-violet-300 border border-violet-500/40 animate-pulse' :
              failed  ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40' :
                        'bg-white/5 text-slate-500 border border-white/10'
            }`}>
              {done ? <CheckCircle2 size={11} /> : active ? <Activity size={11} /> : failed ? <AlertCircle size={11} /> : <Clock size={11} />}
              {STAGE_LABELS[s]}
            </div>
            {i < STAGES.length - 1 && <ChevronRight size={12} className="text-slate-600" />}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── Risk badge ────────────────────────────────────────────────────────────────
function RiskBadge({ level, score }: { level: string; score: number }) {
  const cfg: Record<string, string> = {
    high: 'bg-rose-500/20 text-rose-400 border-rose-500/40',
    medium: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
    low: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
  };
  return (
    <span className={`px-3 py-1 rounded-full text-xs font-bold border uppercase tracking-wider ${cfg[level] || cfg.low}`}>
      {level} ({score})
    </span>
  );
}

// ── Module icon ───────────────────────────────────────────────────────────────
function ModuleIcon({ module }: { module: string }) {
  const icons: Record<string, React.ReactNode> = {
    thermal:  <Thermometer size={16} className="text-orange-400" />,
    audio:    <Mic size={16} className="text-blue-400" />,
    print:    <Box size={16} className="text-purple-400" />,
    specimen: <Microscope size={16} className="text-emerald-400" />,
  };
  return <span>{icons[module] || <Cpu size={16} />}</span>;
}

// ── Finding card ──────────────────────────────────────────────────────────────
function FindingCard({ f }: { f: Finding }) {
  const [open, setOpen] = useState(false);
  const riskColor = { high: 'border-rose-500/50 bg-rose-500/5', medium: 'border-amber-500/50 bg-amber-500/5', low: 'border-emerald-500/50 bg-emerald-500/5' }[f.risk_level] || '';

  return (
    <div className={`border rounded-xl p-4 cursor-pointer transition-all ${riskColor} hover:border-white/20`} onClick={() => setOpen(!open)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle size={13} className={f.risk_level === 'high' ? 'text-rose-400' : f.risk_level === 'medium' ? 'text-amber-400' : 'text-emerald-400'} />
          <span className="text-sm font-medium text-white">{f.short_label || f.label}</span>
          <span className="text-[10px] text-slate-500 font-mono bg-white/5 px-2 py-0.5 rounded">id:{f.id}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-slate-400">sev {(f.severity * 100).toFixed(0)}%</span>
          <ChevronRight size={14} className={`text-slate-500 transition-transform ${open ? 'rotate-90' : ''}`} />
        </div>
      </div>

      {open && (
        <div className="mt-3 pt-3 border-t border-white/10 grid grid-cols-2 gap-3 text-xs">
          <div>
            <p className="text-slate-500 mb-1">Region (px)</p>
            <p className="text-slate-300 font-mono">[{f.region_px.join(', ')}]</p>
          </div>
          <div>
            <p className="text-slate-500 mb-1">Source</p>
            <p className="text-slate-300">{f.source}</p>
          </div>
          {Object.entries(f.measurements || {}).map(([k, v]) => (
            <div key={k}>
              <p className="text-slate-500 mb-1">{k}</p>
              <p className="text-slate-300 font-mono">{String(v)}</p>
            </div>
          ))}
          {f.vision && (
            <div className="col-span-2 bg-violet-500/10 border border-violet-500/30 rounded-lg p-3">
              <p className="text-violet-400 text-[10px] font-bold uppercase mb-1">Vision AI Classification</p>
              <p className="text-white text-xs font-medium">{f.vision.classification}</p>
              <p className="text-slate-400 text-[11px] mt-1">{f.vision.explanation}</p>
              <p className="text-slate-500 text-[10px] mt-1">confidence: {(f.vision.confidence * 100).toFixed(0)}%</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function RunDetailPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.id as string;

  const [job, setJob] = useState<JobData | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>('annotated');
  const [opacity, setOpacity] = useState(40);
  const [activeTab, setActiveTab] = useState<'findings' | 'provenance' | 'eval' | 'simulation'>('findings');
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [remediationStatus, setRemediationStatus] = useState<{ allowed: boolean; reason?: string | null }>({
    allowed: false,
    reason: null,
  });
  const audioRef = useRef<HTMLAudioElement>(null);

  // Poll for job data (SSE reconnect handled here for simplicity)
  const fetchJob = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/jobs/${jobId}`);
      if (res.ok) {
        const data = await res.json();
        setJob(data);
      }
    } catch (e) { /* network error */ }
    finally { setLoading(false); }
  }, [jobId]);

  useEffect(() => {
    fetchJob();
    // Poll every 3s while in-progress
    const interval = setInterval(() => {
      if (job && !['done', 'done_partial', 'done_no_vision', 'failed'].includes(job.status)) {
        fetchJob();
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchJob, job]);

  // Fetch remediation policy status
  useEffect(() => {
    if (jobId) {
      fetch(`${API_BASE}/jobs/${jobId}/views`)
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data?.remediation_status) {
            setRemediationStatus({
              allowed: Boolean(data.remediation_status.allowed),
              reason: data.remediation_status.reason,
            });
          }
        })
        .catch(() => {});
    }
  }, [jobId]);

  // Build view URL client-side
  // Derive which views are available from API response
  const availableViews: string[] = job
    ? Object.keys((job.assets as Record<string, Record<string, string>>)?.views || {})
    : [];

  // Build view URL — all non-base64 (starts with https://) are Cloudinary signed URLs
  const viewUrl = (() => {
    if (!job) return '';
    const views = (job.assets as Record<string, Record<string, string>>)?.views || {};
    // Map view mode to views key
    const key = viewMode as string;
    return views[key] || views.annotated || views.raw || '';
  })();

  // Whether the current view is served from Cloudinary (https URL, not base64)
  const isCldView = viewUrl.startsWith('https://res.cloudinary.com');

  if (loading) return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-slate-400">Loading run…</p>
      </div>
    </div>
  );

  if (!job) return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center text-slate-400">
      <div className="text-center">
        <AlertCircle size={40} className="mx-auto mb-4 text-rose-500" />
        <p className="text-lg font-medium text-white">Run not found</p>
        <p className="text-sm mt-1">Job ID <span className="font-mono">{jobId}</span> does not exist.</p>
        <button onClick={() => router.push('/')} className="mt-4 px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-sm transition-colors">
          ← Back to Dashboard
        </button>
      </div>
    </div>
  );

  const isDone = ['done', 'done_partial', 'done_no_vision'].includes(job.status);
  const isFailed = job.status === 'failed';

  return (
    <div className="min-h-screen bg-[#080c14] text-white">
      {/* Nav */}
      <div className="border-b border-white/10 bg-[#0d1424]/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-[1800px] w-full mx-auto px-6 py-3 flex items-center gap-4">
          <button onClick={() => router.push('/')} className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors text-sm">
            <ArrowLeft size={16} />
            Dashboard
          </button>
          <div className="h-4 w-px bg-white/20" />
          <div className="flex items-center gap-2">
            <ModuleIcon module={job.module} />
            <span className="font-semibold capitalize">{job.module} Analysis</span>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <RiskBadge level={job.risk_level} score={job.risk_score} />
            <ExportMenu
              jobId={job.job_id}
              module={job.module}
              currentView={viewMode}
              availableViews={availableViews.length > 0 ? availableViews : ['raw', 'annotated', 'clean']}
            />
            <button onClick={fetchJob} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors">
              <RefreshCw size={14} />
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-[1800px] w-full mx-auto px-6 py-6 space-y-6">

        {/* Job header */}
        <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-5">
          <div className="flex flex-col md:flex-row md:items-center gap-4">
            <div className="flex-1">
              <p className="text-xs text-slate-500 mb-1 font-mono">{job.job_id}</p>
              <p className="text-white font-medium">{job.summary || 'Processing…'}</p>
              {job.error && (
                <p className="text-rose-400 text-sm mt-1 flex items-center gap-1.5">
                  <AlertCircle size={12} /> {job.error}
                </p>
              )}
            </div>
            <StageStepper stage={job.stage} status={job.status} />
          </div>
        </div>

        <div className={`grid grid-cols-1 ${activeTab === 'simulation' ? 'lg:grid-cols-12' : 'lg:grid-cols-5'} gap-6`}>

          {/* Left: image viewer */}
          <div className={`${activeTab === 'simulation' ? 'lg:col-span-5' : 'lg:col-span-3'} space-y-4`}>

            {/* View mode controls */}
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <ViewTabs
                currentView={viewMode}
                onViewChange={(m) => setViewMode(m)}
                remediationAllowed={remediationStatus.allowed}
                remediationReason={remediationStatus.reason}
                module={job.module}
                availableViews={availableViews}
              />
              {viewMode === 'annotated' && (
                <div className="flex items-center gap-2 ml-auto">
                  <Sliders size={12} className="text-slate-500" />
                  <input
                    type="range" min={10} max={80} value={opacity}
                    onChange={(e) => setOpacity(Number(e.target.value))}
                    className="w-24 accent-violet-500"
                  />
                  <span className="text-xs text-slate-500 w-8">{opacity}%</span>
                </div>
              )}
            </div>

            {viewMode === 'remediation' ? (
              <RemediationView
                jobId={job.job_id}
                module={job.module}
                mode={((job.calibration?.encoding as any)?.mode as string) || '*'}
                findings={job.findings}
                rawImageUrl={(job.assets as any)?.views?.raw || viewUrl}
                annotatedImageUrl={(job.assets as any)?.views?.annotated}
                apiBase={API_BASE}
              />
            ) : (
              <>
                {/* View-specific disclaimers */}
                {viewMode === 'clean' && (
                  <div className="flex items-center gap-2 px-3 py-2 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-300">
                    <Info size={12} />
                    AI Restore (Cloudinary e_gen_restore) — visual enhancement only, not used for measurements.
                  </div>
                )}
                {viewMode === 'upscaled' && (
                  <div className="flex items-center gap-2 px-3 py-2 bg-cyan-500/10 border border-cyan-500/30 rounded-lg text-xs text-cyan-300">
                    <ZoomIn size={12} />
                    4× AI Super-Resolution (Cloudinary e_upscale) — display only. Measurements use original resolution.
                  </div>
                )}
                {viewMode === 'heatmap' && (
                  <div className="flex items-center gap-2 px-3 py-2 bg-orange-500/10 border border-orange-500/30 rounded-lg text-xs text-orange-300">
                    <Info size={12} />
                    Intensity heatmap via Cloudinary tint transform — display only.
                  </div>
                )}
                {viewMode === 'subject_isolated' && (
                  <div className="flex items-center gap-2 px-3 py-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-xs text-emerald-300">
                    <Info size={12} />
                    Subject isolation via Cloudinary e_background_removal — display only.
                  </div>
                )}
                {isCldView && (
                  <div className="flex items-center gap-1.5 px-2 py-1 bg-cyan-900/20 border border-cyan-700/30 rounded-lg text-[10px] text-cyan-400 font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse inline-block" />
                    Cloudinary AI · signed delivery · q_auto · f_auto
                  </div>
                )}

                {/* Image display */}
                <div className="relative bg-black/40 border border-white/10 rounded-2xl overflow-hidden min-h-[320px] flex items-center justify-center">
                  {viewUrl ? (
                    <img src={viewUrl} alt={`${viewMode} view`} className="w-full h-auto rounded-2xl object-contain max-h-[480px]" />
                  ) : (
                    <div className="text-center text-slate-600 py-16">
                      <Cpu size={40} className="mx-auto mb-3" />
                      <p className="text-sm">{isDone ? 'No preview available' : 'Processing image…'}</p>
                    </div>
                  )}
                  {!isDone && !isFailed && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-2xl">
                      <div className="text-center">
                        <div className="w-10 h-10 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                        <p className="text-slate-300 text-sm capitalize">{job.stage}…</p>
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* Audio player for Module D */}
            {job.module === 'audio' && (
              <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4">
                <p className="text-xs text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <Volume2 size={11} /> Audio Player
                </p>

                {/* Waveform image */}
                {(() => {
                  const assets = job.assets as Record<string, unknown>;
                  const waveformSrc =
                    (assets.waveform_b64 as string) ||
                    (CLD_CLOUD && (assets.waveform as Record<string, string>)?.public_id
                      ? `https://res.cloudinary.com/${CLD_CLOUD}/video/authenticated/fl_waveform,f_png/${(assets.waveform as Record<string, string>).public_id}`
                      : '');
                  return waveformSrc ? (
                    <img
                      src={waveformSrc}
                      alt="Audio waveform"
                      className="mb-3 w-full h-16 object-cover rounded-lg opacity-80"
                    />
                  ) : null;
                })()}

                {/* Playback controls */}
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => {
                      const el = audioRef.current;
                      if (!el) return;
                      if (audioPlaying) { el.pause(); setAudioPlaying(false); }
                      else { el.play().catch(() => {}); setAudioPlaying(true); }
                    }}
                    className="w-9 h-9 flex items-center justify-center rounded-full bg-blue-600/30 border border-blue-500/40 text-blue-300 hover:bg-blue-600/50 transition-all shrink-0"
                  >
                    {audioPlaying ? <Pause size={14} /> : <Play size={14} />}
                  </button>

                  {/* Scrub bar */}
                  <div
                    className="relative flex-1 h-1.5 bg-white/10 rounded-full cursor-pointer"
                    onClick={(e) => {
                      const el = audioRef.current;
                      if (!el || !audioDuration) return;
                      const rect = e.currentTarget.getBoundingClientRect();
                      el.currentTime = ((e.clientX - rect.left) / rect.width) * audioDuration;
                    }}
                  >
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: audioDuration ? `${(audioProgress / audioDuration) * 100}%` : '0%' }}
                    />
                  </div>

                  <span className="text-xs text-slate-500 font-mono w-20 text-right">
                    {Math.floor(audioProgress / 60)}:{String(Math.floor(audioProgress % 60)).padStart(2, '0')}
                    {' / '}
                    {audioDuration ? `${Math.floor(audioDuration / 60)}:${String(Math.floor(audioDuration % 60)).padStart(2, '0')}` : '--:--'}
                  </span>
                </div>

                {/* Hidden <audio> element — src must be the actual audio bytes, NOT the spectrogram image */}
                {(() => {
                  const assets = job.assets as Record<string, string>;
                  // audio_src = data:audio/wav;base64,... stored by backend after processing
                  // Fall back to Cloudinary raw URL if available
                  const audioSrc = assets.audio_src ||
                    ((assets as any).views?.audio_url) || '';
                  return audioSrc ? (
                    <audio
                      ref={audioRef}
                      src={audioSrc}
                      onEnded={() => { setAudioPlaying(false); setAudioProgress(0); }}
                      onTimeUpdate={() => setAudioProgress(audioRef.current?.currentTime ?? 0)}
                      onLoadedMetadata={() => setAudioDuration(audioRef.current?.duration ?? 0)}
                      preload="metadata"
                    />
                  ) : (
                    <p className="text-[11px] text-rose-400 mt-2 flex items-center gap-1">
                      <AlertCircle size={11} /> Audio source unavailable — re-upload to regenerate.
                    </p>
                  );
                })()}
              </div>
            )}

            {/* Bandwidth card */}
            <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4 flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Delivery Optimisation</p>
                <p className="text-[11px] text-slate-400">Cloudinary <code className="text-violet-400">f_auto,q_auto</code> applied</p>
              </div>
              <div className="text-right">
                <p className="text-xs text-slate-500 mb-0.5">Format</p>
                <p className="text-sm font-bold text-emerald-400">WebP / AVIF</p>
              </div>
            </div>
          </div>

          {/* Right: tabs panel */}
          <div className={`${activeTab === 'simulation' ? 'lg:col-span-7' : 'lg:col-span-2'} space-y-4`}>
            <div className="flex gap-1 bg-white/5 p-1 rounded-xl border border-white/10">
              {([['findings', 'Findings'], ['simulation', 'Simulation Lab'], ['provenance', 'Provenance'], ['eval', 'Eval']] as const).map(([tab, label]) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    activeTab === tab ? 'bg-violet-600/30 text-violet-300' : 'text-slate-500 hover:text-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Simulation Lab tab */}
            {activeTab === 'simulation' && (
              <SimulationPanel
                jobId={job.job_id}
                module={job.module}
                mode={((job.calibration?.encoding as any)?.mode as string) || '*'}
                rawImageUrl={(job.assets as any)?.views?.raw || viewUrl}
                apiBase={API_BASE}
              />
            )}

            {/* Findings tab */}
            {activeTab === 'findings' && (
              <div className="space-y-2">
                {job.findings.length === 0 ? (
                  <div className="text-center py-8 text-slate-600">
                    <ShieldCheck size={28} className="mx-auto mb-2 text-emerald-600" />
                    <p className="text-sm">{isDone ? 'No anomalies detected' : 'Awaiting analysis…'}</p>
                  </div>
                ) : (
                  job.findings.map(f => <FindingCard key={f.id} f={f} />)
                )}
              </div>
            )}

            {/* Provenance tab */}
            {activeTab === 'provenance' && (
              <div className="space-y-3 text-xs">
                {job.provenance ? (
                  <>
                    <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4">
                      <p className="text-slate-500 mb-2 uppercase tracking-wider text-[10px]">Deterministic Steps</p>
                      <div className="space-y-1">
                        {job.provenance.deterministic_steps?.map(s => (
                          <div key={s} className="flex items-center gap-2 text-emerald-300">
                            <CheckCircle2 size={10} /> <span className="font-mono">{s}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    {(job.provenance.generative_steps?.length ?? 0) > 0 && (
                      <div className="bg-white/[0.03] border border-amber-500/20 rounded-xl p-4">
                        <p className="text-amber-400 mb-2 uppercase tracking-wider text-[10px] flex items-center gap-1">
                          <Info size={10} /> Cosmetic Generative Steps (display only)
                        </p>
                        {job.provenance.generative_steps?.map((s, i) => (
                          <div key={i} className="text-amber-300/70 font-mono">{s.step} — {s.purpose}</div>
                        ))}
                      </div>
                    )}
                    {job.provenance.vision && (
                      <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4">
                        <p className="text-slate-500 mb-2 uppercase tracking-wider text-[10px]">Vision Provider</p>
                        <p className="text-white font-medium">{job.provenance.vision.provider}</p>
                        <p className="text-slate-400 mt-1">{job.provenance.vision.model}</p>
                        <p className="text-slate-500 font-mono text-[10px] mt-1">prompt v{job.provenance.vision.prompt_version}</p>
                      </div>
                    )}
                    {job.provenance.input_hash && (
                      <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4">
                        <p className="text-slate-500 mb-1 uppercase tracking-wider text-[10px]">Input Hash</p>
                        <p className="font-mono text-[10px] text-slate-400 break-all">{job.provenance.input_hash}</p>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-slate-500 text-center py-6">Provenance unavailable</p>
                )}
              </div>
            )}

            {/* Eval tab */}
            {activeTab === 'eval' && (
              <div className="text-xs space-y-3">
                <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4">
                  <p className="text-slate-500 uppercase tracking-wider text-[10px] mb-3 flex items-center gap-1.5">
                    <BarChart3 size={10} /> Module Evaluation Metrics
                  </p>
                  <div className="space-y-2 text-slate-400">
                    <p>Run <code className="text-violet-400">python api/eval/run_eval.py --module {job.module}</code> to see full precision/recall numbers.</p>
                    <p className="text-[10px] text-slate-600 mt-2">All metrics computed on synthetic fixtures in CI. Real dataset results in <code>docs/eval_results.md</code>.</p>
                  </div>
                </div>
                <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4">
                  <p className="text-slate-500 uppercase tracking-wider text-[10px] mb-2">Disclaimer</p>
                  <p className="text-slate-500">Results are for research and screening purposes only. Not a certified diagnostic device.</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
