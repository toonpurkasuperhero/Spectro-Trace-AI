'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft, Search, Filter, RefreshCw, CheckCircle2, AlertTriangle,
  Clock, Thermometer, Mic, Box, Microscope, ChevronRight, Eye,
  ShieldCheck, ExternalLink, AlertCircle, Flame, Activity
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

// ── Types ─────────────────────────────────────────────────────────────────────
interface HistoryItem {
  public_id?: string;
  job_id?: string;
  module?: string;
  tags?: string[];
  metadata?: { risk_level?: string; risk_score?: number; review_state?: string };
  risk_level?: string;
  risk_score?: number;
  review_state?: string;   // top-level field for local in-memory jobs
  status?: string;
  summary?: string;
  created_at?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function extractModule(item: HistoryItem): string {
  if (item.module) return item.module;
  const tag = item.tags?.find(t => t.startsWith('module:'));
  return tag ? tag.split(':')[1] : '—';
}

function extractRisk(item: HistoryItem): { level: string; score: number } {
  return {
    level: item.metadata?.risk_level || item.risk_level || 'unknown',
    score: item.metadata?.risk_score ?? item.risk_score ?? 0,
  };
}

function extractReviewState(item: HistoryItem): string {
  // Local in-memory jobs expose review_state at the top level;
  // Cloudinary Search API results expose it under metadata.
  return (item as any).review_state || item.metadata?.review_state || 'pending';
}

function extractId(item: HistoryItem): string {
  return item.public_id || item.job_id || '';
}

// ── Sub-components ────────────────────────────────────────────────────────────
const MODULE_ICONS: Record<string, React.ReactNode> = {
  thermal:  <Thermometer size={14} className="text-orange-400" />,
  audio:    <Mic size={14} className="text-blue-400" />,
  print:    <Box size={14} className="text-purple-400" />,
  specimen: <Microscope size={14} className="text-emerald-400" />,
};

const RISK_STYLES: Record<string, string> = {
  high:    'bg-rose-500/15 text-rose-400 border-rose-500/40',
  medium:  'bg-amber-500/15 text-amber-400 border-amber-500/40',
  low:     'bg-emerald-500/15 text-emerald-400 border-emerald-500/40',
  unknown: 'bg-slate-500/15 text-slate-400 border-slate-500/40',
};

const REVIEW_STYLES: Record<string, string> = {
  approved: 'text-emerald-400',
  rejected: 'text-rose-400',
  pending:  'text-amber-400',
};

function RiskBadge({ level, score }: { level: string; score: number }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold border uppercase tracking-wider ${RISK_STYLES[level] || RISK_STYLES.unknown}`}>
      {level} ({score})
    </span>
  );
}

// ── Filters bar ───────────────────────────────────────────────────────────────
const MODULES  = ['all', 'thermal', 'audio', 'print', 'specimen'];
const RISKS    = ['all', 'high', 'medium', 'low'];
const REVIEWS  = ['all', 'pending', 'approved', 'rejected'];

function FiltersBar({
  module, risk, review, search,
  onModule, onRisk, onReview, onSearch,
}: {
  module: string; risk: string; review: string; search: string;
  onModule: (v: string) => void; onRisk: (v: string) => void;
  onReview: (v: string) => void; onSearch: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Search */}
      <div className="relative">
        <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
        <input
          type="text" value={search} onChange={e => onSearch(e.target.value)}
          placeholder="Search runs…"
          className="pl-8 pr-3 py-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white placeholder-slate-600 outline-none focus:border-violet-500/50 w-44"
        />
      </div>

      {/* Module filter */}
      <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-lg p-1">
        {MODULES.map(m => (
          <button key={m} onClick={() => onModule(m)}
            className={`px-2.5 py-1 rounded text-[11px] font-medium capitalize transition-all ${
              module === m ? 'bg-violet-600/30 text-violet-300' : 'text-slate-500 hover:text-white'
            }`}
          >
            {m === 'all' ? 'All Modules' : m}
          </button>
        ))}
      </div>

      {/* Risk filter */}
      <select
        value={risk} onChange={e => onRisk(e.target.value)}
        className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-slate-300 outline-none focus:border-violet-500/50 capitalize"
      >
        {RISKS.map(r => <option key={r} value={r} className="bg-slate-900">{r === 'all' ? 'All Risk Levels' : r.toUpperCase()}</option>)}
      </select>

      {/* Review state filter */}
      <select
        value={review} onChange={e => onReview(e.target.value)}
        className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-slate-300 outline-none focus:border-violet-500/50"
      >
        {REVIEWS.map(r => <option key={r} value={r} className="bg-slate-900">{r === 'all' ? 'All States' : r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
      </select>
    </div>
  );
}

// ── Review action button ──────────────────────────────────────────────────────
function ReviewButton({
  jobId, currentState, onUpdated,
}: { jobId: string; currentState: string; onUpdated: () => void }) {
  const [loading, setLoading] = useState(false);
  // Optimistic local state — flips immediately on click
  const [localState, setLocalState] = useState(currentState);

  // Keep in sync if parent re-renders with a new value (e.g., after re-fetch)
  React.useEffect(() => { setLocalState(currentState); }, [currentState]);

  const update = async (state: 'approved' | 'rejected') => {
    setLoading(true);
    setLocalState(state);   // optimistic update — show result immediately
    try {
      const res = await fetch(`${API_BASE}/jobs/${jobId}/review`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ review_state: state }),
      });
      if (!res.ok) {
        // Roll back if request failed
        setLocalState(currentState);
      } else {
        onUpdated();
      }
    } catch {
      setLocalState(currentState);
    } finally {
      setLoading(false);
    }
  };

  if (localState === 'approved') return (
    <span className="text-[11px] text-emerald-400 flex items-center gap-1"><CheckCircle2 size={11} /> Approved</span>
  );
  if (localState === 'rejected') return (
    <span className="text-[11px] text-rose-400 flex items-center gap-1"><AlertCircle size={11} /> Rejected</span>
  );

  return (
    <div className="flex gap-1">
      <button
        disabled={loading} onClick={() => update('approved')}
        className="px-2.5 py-1 text-[10px] rounded-lg bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/40 transition-colors disabled:opacity-50 flex items-center gap-1 font-medium"
      >
        {loading ? <span className="w-2.5 h-2.5 rounded-full border border-emerald-400 border-t-transparent animate-spin" /> : <CheckCircle2 size={10} />}
        Approve
      </button>
      <button
        disabled={loading} onClick={() => update('rejected')}
        className="px-2.5 py-1 text-[10px] rounded-lg bg-rose-500/20 border border-rose-500/30 text-rose-400 hover:bg-rose-500/40 transition-colors disabled:opacity-50 flex items-center gap-1 font-medium"
      >
        {loading ? <span className="w-2.5 h-2.5 rounded-full border border-rose-400 border-t-transparent animate-spin" /> : <AlertCircle size={10} />}
        Reject
      </button>
    </div>
  );
}

// ── History row ───────────────────────────────────────────────────────────────
function HistoryRow({ item, onUpdated }: { item: HistoryItem; onUpdated: () => void }) {
  const router = useRouter();
  const mod = extractModule(item);
  const { level, score } = extractRisk(item);
  const review = extractReviewState(item);
  const id = extractId(item);
  const ts = item.created_at ? new Date(item.created_at).toLocaleString() : '—';

  return (
    <tr className="border-b border-white/5 hover:bg-white/[0.02] transition-colors group">
      <td className="py-3 px-4">
        <span className="font-mono text-[11px] text-slate-400 truncate max-w-[180px] block">{id}</span>
      </td>
      <td className="py-3 px-4">
        <span className="flex items-center gap-2 capitalize text-sm text-white">
          {MODULE_ICONS[mod]}
          {mod}
        </span>
      </td>
      <td className="py-3 px-4">
        <RiskBadge level={level} score={score} />
      </td>
      <td className="py-3 px-4">
        <span className={`text-sm capitalize ${REVIEW_STYLES[review] || REVIEW_STYLES.pending}`}>{review}</span>
      </td>
      <td className="py-3 px-4 text-xs text-slate-500">{ts}</td>
      <td className="py-3 px-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push(`/runs/${encodeURIComponent(id)}`)}
            className="px-2.5 py-1 rounded bg-slate-800 text-slate-300 hover:text-white border border-white/10 text-[11px] flex items-center gap-1 transition-colors"
          >
            <Eye size={10} /> Inspect
          </button>
          <ReviewButton jobId={id} currentState={review} onUpdated={onUpdated} />
        </div>
      </td>
    </tr>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────
function EmptyState({ filtered }: { filtered: boolean }) {
  return (
    <tr>
      <td colSpan={6} className="py-16 text-center">
        <ShieldCheck size={32} className="mx-auto mb-3 text-slate-700" />
        <p className="text-slate-500 font-medium">
          {filtered ? 'No runs match your filters.' : 'No analysis runs yet.'}
        </p>
        <p className="text-slate-600 text-sm mt-1">
          {filtered ? 'Try adjusting the filters above.' : 'Upload a file on the Dashboard to get started.'}
        </p>
      </td>
    </tr>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [module, setModule]   = useState('all');
  const [risk, setRisk]       = useState('all');
  const [review, setReview]   = useState('all');
  const [search, setSearch]   = useState('');

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (module !== 'all') params.set('module', module);
      if (risk !== 'all')   params.set('risk', risk);
      const res = await fetch(`${API_BASE}/history?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        // Cloudinary Search API returns { resources: [...] }; fallback returns { resources: [...] } too
        setItems(data.resources || data || []);
      }
    } catch (e) { /* */ }
    finally { setLoading(false); }
  }, [module, risk]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  // Client-side review & search filtering
  const filtered = items.filter(item => {
    const id = extractId(item).toLowerCase();
    if (search && !id.includes(search.toLowerCase())) return false;
    if (review !== 'all' && extractReviewState(item) !== review) return false;
    return true;
  });

  const stats = {
    total: items.length,
    high:  items.filter(i => extractRisk(i).level === 'high').length,
    pending: items.filter(i => extractReviewState(i) === 'pending').length,
  };

  return (
    <div className="min-h-screen bg-[#080c14] text-white">
      {/* Nav */}
      <div className="border-b border-white/10 bg-[#0d1424]/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-4">
          <button onClick={() => router.push('/')} className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors text-sm">
            <ArrowLeft size={16} />
            Dashboard
          </button>
          <div className="h-4 w-px bg-white/20" />
          <span className="font-semibold text-white">History & Review Queue</span>
          <div className="ml-auto">
            <button onClick={fetchHistory} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5">
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">

        {/* Stats strip */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Total Runs', value: stats.total, icon: <Activity size={16} className="text-violet-400" />, color: 'text-white' },
            { label: 'High Risk', value: stats.high,   icon: <Flame size={16} className="text-rose-400" />,     color: 'text-rose-400' },
            { label: 'Pending Review', value: stats.pending, icon: <Clock size={16} className="text-amber-400" />, color: 'text-amber-400' },
          ].map(({ label, value, icon, color }) => (
            <div key={label} className="bg-white/[0.03] border border-white/10 rounded-xl p-4 flex items-center gap-4">
              <div className="w-9 h-9 rounded-lg bg-white/5 flex items-center justify-center">{icon}</div>
              <div>
                <p className="text-xs text-slate-500">{label}</p>
                <p className={`text-2xl font-bold ${color}`}>{value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <FiltersBar
          module={module} risk={risk} review={review} search={search}
          onModule={setModule} onRisk={setRisk} onReview={setReview} onSearch={setSearch}
        />

        {/* Table */}
        <div className="bg-white/[0.02] border border-white/10 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10 text-xs text-slate-500 uppercase tracking-wider">
                  <th className="py-3 px-4 text-left">Asset / Job ID</th>
                  <th className="py-3 px-4 text-left">Module</th>
                  <th className="py-3 px-4 text-left">Risk</th>
                  <th className="py-3 px-4 text-left">Review</th>
                  <th className="py-3 px-4 text-left">Created</th>
                  <th className="py-3 px-4 text-left">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center">
                      <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                      <p className="text-slate-500 text-sm">Loading history…</p>
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <EmptyState filtered={search !== '' || review !== 'all'} />
                ) : (
                  filtered.map((item, i) => (
                    <HistoryRow key={extractId(item) || i} item={item} onUpdated={fetchHistory} />
                  ))
                )}
              </tbody>
            </table>
          </div>
          {filtered.length > 0 && (
            <div className="px-4 py-2 border-t border-white/5 text-xs text-slate-600 text-right">
              Showing {filtered.length} of {items.length} runs · powered by Cloudinary Search API
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
