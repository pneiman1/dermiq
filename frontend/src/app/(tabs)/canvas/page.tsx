"use client";

import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
// react-grid-layout ships a CJS `export =`; import the namespace and resolve the
// grid component + WidthProvider HOC from it (named/default interop is unreliable
// for this package under Next/webpack).
import * as ReactGridLayout from "react-grid-layout";
import { Sparkles, Send, RefreshCw, Trash2, ChevronDown, Save } from "lucide-react";

type RGLayout = { i: string; x: number; y: number; w: number; h: number };

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { CanvasChart, CanvasSummary, ChartSpec } from "@/lib/types";
import { KPIChart } from "@/components/canvas/KPIChart";
import { BarChart } from "@/components/canvas/BarChart";
import { LineChart } from "@/components/canvas/LineChart";
import { ScatterChart } from "@/components/canvas/ScatterChart";
import { PieChart } from "@/components/canvas/PieChart";
import { TableChart } from "@/components/canvas/TableChart";

/* eslint-disable @typescript-eslint/no-explicit-any */
const RGLModule = ReactGridLayout as any;
const GridLayoutCmp = RGLModule.default ?? RGLModule;
const WidthProvider = RGLModule.WidthProvider ?? GridLayoutCmp.WidthProvider;
const Grid = WidthProvider(GridLayoutCmp);
const LS_KEY = "dermiq.canvas.v1";

const FALLBACK_CHIPS = [
  "Revenue by provider (bar chart)",
  "No-show rate over last 90 days (line)",
  "LTV vs CAC by channel (scatter)",
  "Category revenue mix (pie)",
  "Top 10 recall patients (table)",
  "Total revenue KPI with prior-period comparison",
];

const FOLLOWUP_CHIPS = [
  "True margin by service (bar chart)",
  "Inventory value by category (pie)",
  "Provider revenue per hour (bar chart)",
  "Days of supply by SKU (table)",
];

// ~30 example prompts for autocomplete (prefix match).
const EXAMPLES = [
  "Revenue by provider (bar chart)",
  "Revenue trends over the last 6 months",
  "No-show rate over last 90 days (line)",
  "LTV vs CAC by channel (scatter)",
  "Category revenue mix (pie)",
  "Top 10 recall patients (table)",
  "Total revenue KPI with prior-period comparison",
  "Make me a scatter of visits vs revenue by provider",
  "Which channels are unprofitable?",
  "Spend by acquisition channel",
  "Patients acquired by channel",
  "True margin by service",
  "Services where true margin is below catalog margin",
  "Inventory value by category",
  "Stock status by SKU",
  "Days of supply by SKU",
  "Lots expiring soon by value at risk",
  "Waste cost by service",
  "Patient segments by size",
  "Average LTV by segment",
  "Provider revenue per hour",
  "Cross-sell rate by provider",
  "Skincare attach rate by provider",
  "Recall queue by priority",
  "Revenue at risk by recall priority",
  "Daily net revenue over time",
  "New patients per day",
  "Average ticket by provider",
  "Consumables cost by service",
  "Expiring inventory by urgency",
];

function renderChart(spec: ChartSpec, data: CanvasChart["data"]) {
  switch (spec.type) {
    case "kpi":
      return <KPIChart spec={spec} data={data} />;
    case "bar":
      return <BarChart spec={spec} data={data} />;
    case "line":
      return <LineChart spec={spec} data={data} />;
    case "scatter":
      return <ScatterChart spec={spec} data={data} />;
    case "pie":
      return <PieChart spec={spec} data={data} />;
    case "table":
      return <TableChart spec={spec} data={data} />;
  }
}

export default function CanvasPage() {
  const [charts, setCharts] = useState<CanvasChart[]>([]);
  const [layout, setLayout] = useState<RGLayout[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [acOpen, setAcOpen] = useState(false);
  const [acIndex, setAcIndex] = useState(0);
  const [saved, setSaved] = useState<CanvasSummary[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const nextId = useRef(1);

  // Restore from localStorage on mount.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) {
        const s = JSON.parse(raw);
        setCharts(s.charts ?? []);
        setLayout(s.layout ?? []);
        nextId.current = (s.charts?.length ?? 0) + 1;
      }
    } catch {
      /* ignore corrupt state */
    }
  }, []);

  // Persist to localStorage on every change.
  useEffect(() => {
    localStorage.setItem(LS_KEY, JSON.stringify({ charts, layout }));
  }, [charts, layout]);

  const refreshSaved = useCallback(() => {
    api.listCanvases().then(setSaved).catch(() => setSaved([]));
  }, []);
  useEffect(() => {
    refreshSaved();
  }, [refreshSaved]);

  const chips = charts.length === 0 ? FALLBACK_CHIPS : FOLLOWUP_CHIPS;

  const acMatches = useMemo(() => {
    const q = input.trim().toLowerCase();
    if (!q) return [];
    return EXAMPLES.filter((e) => e.toLowerCase().startsWith(q) && e.toLowerCase() !== q).slice(0, 6);
  }, [input]);

  async function submit(prompt: string) {
    const text = prompt.trim();
    if (!text || loading) return;
    setInput("");
    setAcOpen(false);
    setError(null);
    setLoading(true);
    const id = String(nextId.current++);
    const placeholderId = `pending-${id}`;
    setPendingId(placeholderId);
    // Drop a shimmer placeholder into the grid immediately.
    setLayout((l) => [...l, { i: placeholderId, x: (charts.length * 6) % 12, y: Infinity, w: 6, h: 9 }]);
    try {
      const existing = charts.map((c) => c.spec);
      const res = await api.generateChart(text, existing);
      const chart: CanvasChart = {
        i: id,
        spec: res.chart_spec,
        data: res.resolved_data,
        reasoning: res.reasoning,
        warnings: res.warnings,
      };
      setCharts((c) => [...c, chart]);
      setLayout((l) => [
        ...l.filter((x) => x.i !== placeholderId),
        { i: id, x: (charts.length * 6) % 12, y: Infinity, w: 6, h: 9 },
      ]);
    } catch (e) {
      setLayout((l) => l.filter((x) => x.i !== placeholderId));
      setError(e instanceof Error ? e.message : "Something went wrong generating that chart.");
    } finally {
      setLoading(false);
      setPendingId(null);
    }
  }

  async function refreshChart(chart: CanvasChart) {
    try {
      const { data } = await api.queryChart(chart.spec);
      setCharts((cs) => cs.map((c) => (c.i === chart.i ? { ...c, data } : c)));
    } catch {
      /* leave existing data */
    }
  }

  function removeChart(id: string) {
    if (!confirm("Delete this chart?")) return;
    setCharts((cs) => cs.filter((c) => c.i !== id));
    setLayout((l) => l.filter((x) => x.i !== id));
  }

  async function saveCurrent() {
    const title = prompt("Name this canvas:");
    if (!title) return;
    await api.saveCanvas(title, charts.map((c) => c.spec), layout);
    refreshSaved();
    setMenuOpen(false);
  }

  async function loadCanvas(id: string) {
    setMenuOpen(false);
    const c = await api.loadCanvas(id);
    // Re-run each spec to get fresh data.
    const loaded: CanvasChart[] = [];
    for (let i = 0; i < c.charts.length; i++) {
      const spec = c.charts[i];
      try {
        const { data } = await api.queryChart(spec);
        loaded.push({ i: String(i), spec, data, reasoning: "", warnings: [] });
      } catch {
        loaded.push({ i: String(i), spec, data: [], reasoning: "", warnings: [] });
      }
    }
    nextId.current = loaded.length + 1;
    setCharts(loaded);
    setLayout((c.layout as RGLayout[]) ?? []);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (acOpen && acMatches.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setAcIndex((i) => (i + 1) % acMatches.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setAcIndex((i) => (i - 1 + acMatches.length) % acMatches.length);
        return;
      }
      if (e.key === "Enter" && acOpen) {
        e.preventDefault();
        submit(acMatches[acIndex]);
        return;
      }
      if (e.key === "Escape") {
        setAcOpen(false);
        return;
      }
    }
    if (e.key === "Enter") {
      e.preventDefault();
      submit(input);
    }
  }

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-start justify-between">
        <PageHeader title="Canvas" subtitle="Ask for any visualization" />
        {/* Saved canvases dropdown */}
        <div className="relative">
          <Button variant="outline" size="sm" onClick={() => setMenuOpen((o) => !o)}>
            Saved canvases
            <ChevronDown className="ml-1 h-3.5 w-3.5" />
          </Button>
          {menuOpen && (
            <div className="absolute right-0 z-20 mt-1 w-64 rounded-md border border-border bg-card p-1 shadow-lg">
              <button
                onClick={saveCurrent}
                className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <Save className="h-3.5 w-3.5" /> Save current canvas…
              </button>
              <div className="my-1 h-px bg-border" />
              {saved.length === 0 ? (
                <p className="px-3 py-2 text-xs text-muted-foreground">No saved canvases yet.</p>
              ) : (
                saved.map((s) => (
                  <button
                    key={s.canvas_id}
                    onClick={() => loadCanvas(s.canvas_id)}
                    className="block w-full truncate rounded px-3 py-2 text-left text-sm hover:bg-muted"
                  >
                    {s.title}
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* Grid area (scrolls; leaves room for the sticky composer) */}
      <div className="mt-4 flex-1 overflow-y-auto pb-40">
        {charts.length === 0 && !pendingId ? (
          <div className="flex h-full min-h-[300px] flex-col items-center justify-center text-center">
            <Sparkles className="h-12 w-12 text-slate-300" />
            <p className="mt-3 text-sm text-muted-foreground">
              Type a request below to add your first chart
            </p>
          </div>
        ) : (
          <Grid
            className="layout"
            layout={layout}
            cols={12}
            rowHeight={32}
            margin={[16, 16]}
            onLayoutChange={setLayout}
            draggableCancel=".no-drag"
            isBounded
          >
            {charts.map((chart) => (
              <div key={chart.i}>
                <Card className="group flex h-full flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-300">
                  <div className="flex items-start justify-between gap-2 border-b border-border px-4 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{chart.spec.title}</p>
                      {chart.reasoning && (
                        <p className="truncate text-[12px] italic text-slate-500">{chart.reasoning}</p>
                      )}
                    </div>
                    <div className="no-drag flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <button onClick={() => refreshChart(chart)} title="Refresh" className="rounded p-1 hover:bg-muted">
                        <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
                      </button>
                      <button onClick={() => removeChart(chart.i)} title="Delete" className="rounded p-1 hover:bg-muted">
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </button>
                    </div>
                  </div>
                  <CardContent className="no-drag min-h-0 flex-1 p-3">
                    {renderChart(chart.spec, chart.data)}
                  </CardContent>
                </Card>
              </div>
            ))}
            {pendingId && (
              <div key={pendingId}>
                <Card className="flex h-full items-center justify-center overflow-hidden">
                  <div className="h-full w-full animate-pulse rounded-lg bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-800 dark:to-slate-900" />
                </Card>
              </div>
            )}
          </Grid>
        )}
      </div>

      {/* Sticky composer */}
      <div className="absolute inset-x-0 bottom-0 border-t border-border bg-card/80 p-4 backdrop-blur">
        {error && (
          <div className="mb-2 flex items-center justify-between rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            <span>{error}</span>
            <button onClick={() => submit(input || (charts.at(-1)?.spec.title ?? ""))} className="flex items-center gap-1 text-xs font-medium">
              <RefreshCw className="h-3 w-3" /> Retry
            </button>
          </div>
        )}
        <div className="mb-2 flex flex-wrap gap-2">
          {chips.map((c) => (
            <button
              key={c}
              onClick={() => submit(c)}
              disabled={loading}
              className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:opacity-50"
            >
              {c}
            </button>
          ))}
        </div>
        <div className="relative">
          {acOpen && acMatches.length > 0 && (
            <div className="absolute bottom-[56px] left-0 z-20 w-full overflow-hidden rounded-md border border-border bg-card shadow-lg">
              {acMatches.map((m, i) => (
                <button
                  key={m}
                  onMouseEnter={() => setAcIndex(i)}
                  onClick={() => submit(m)}
                  className={cn("block w-full px-3 py-2 text-left text-sm", i === acIndex ? "bg-muted" : "hover:bg-muted")}
                >
                  {m}
                </button>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2">
            <input
              value={input}
              disabled={loading}
              onChange={(e) => {
                setInput(e.target.value);
                setAcOpen(true);
                setAcIndex(0);
              }}
              onKeyDown={onKeyDown}
              onBlur={() => setTimeout(() => setAcOpen(false), 150)}
              placeholder="Ask for any visualization... e.g. show me revenue by provider"
              className="h-[52px] flex-1 rounded-lg border border-border bg-background px-4 text-sm outline-none focus:border-primary/50 disabled:opacity-60"
            />
            <button
              onClick={() => submit(input)}
              disabled={loading || !input.trim()}
              className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
              title="Generate"
            >
              {loading ? <RefreshCw className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
