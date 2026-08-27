"use client";

import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { Activity, AlertTriangle, Banknote, CheckCircle2, Gauge, RefreshCw, ShieldAlert } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { MetricCard } from "@/components/metric-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch } from "@/lib/api";
import type { Alert, DriftReport, ModelInfo, ModelPerformance, Overview, PageResult, PerformanceReport, RetrainingJob, TransactionSummary, TrendPoint } from "@/lib/types";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const number = new Intl.NumberFormat("en-US");
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 });

function decisionTone(decision: string) {
  if (decision === "BLOCK") return "danger" as const;
  if (decision === "MANUAL_REVIEW") return "warning" as const;
  return "success" as const;
}

const column = createColumnHelper<TransactionSummary>();
const transactionColumns = [
  column.accessor("transaction_id", {
    header: "Transaction",
    cell: ({ getValue }) => <span className="font-mono text-xs">{getValue()}</span>,
  }),
  column.accessor("amount", {
    header: "Amount",
    cell: ({ row, getValue }) => money.format(getValue()) + ` ${row.original.currency}`,
  }),
  column.accessor("country", { header: "Country" }),
  column.accessor("risk_score", {
    header: "Risk",
    cell: ({ getValue }) => <span className="font-mono">{getValue()}</span>,
  }),
  column.accessor("decision", {
    header: "Decision",
    cell: ({ getValue }) => <Badge tone={decisionTone(getValue())}>{getValue()}</Badge>,
  }),
];

function DataState({ loading, error }: { loading: boolean; error: Error | null }) {
  if (loading) return <p className="p-6 text-sm text-muted-foreground">Loading live platform data…</p>;
  if (error) return <p className="p-6 text-sm text-red-300">{error.message}</p>;
  return null;
}

export function CommandCenter() {
  const queryClient = useQueryClient();
  const results = useQueries({
    queries: [
      { queryKey: ["overview"], queryFn: () => apiFetch<Overview>("analytics/overview") },
      { queryKey: ["trends"], queryFn: () => apiFetch<TrendPoint[]>("analytics/fraud-trends?dimension=hour&hours=24") },
      { queryKey: ["transactions"], queryFn: () => apiFetch<PageResult<TransactionSummary>>("transactions?limit=25") },
      { queryKey: ["alerts"], queryFn: () => apiFetch<Alert[]>("alerts?limit=100") },
      { queryKey: ["performance"], queryFn: () => apiFetch<ModelPerformance>("analytics/model-performance") },
      { queryKey: ["model"], queryFn: () => apiFetch<ModelInfo>("model/info") },
      { queryKey: ["drift"], queryFn: () => apiFetch<PageResult<DriftReport>>("analytics/drift-reports?limit=20") },
      { queryKey: ["performance-history"], queryFn: () => apiFetch<PerformanceReport[]>("analytics/performance-reports?limit=20") },
      { queryKey: ["retraining-jobs"], queryFn: () => apiFetch<RetrainingJob[]>("admin/retraining-jobs") },
    ],
  });
  const [overview, trends, transactions, alerts, performance, model, drift, performanceHistory, retrainingJobs] = results;
  // TanStack Table exposes intentionally non-memoizable functions.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: transactions.data?.items ?? [],
    columns: transactionColumns,
    getCoreRowModel: getCoreRowModel(),
  });
  const resolveAlert = useMutation({
    mutationFn: ({ alertId, resolution }: { alertId: number; resolution: "FRAUD" | "LEGITIMATE" }) =>
      apiFetch(`alerts/${alertId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "RESOLVED", resolution }),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["alerts"] }),
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
        queryClient.invalidateQueries({ queryKey: ["performance"] }),
      ]);
    },
  });
  const requestRetraining = useMutation({
    mutationFn: () => apiFetch<RetrainingJob>("admin/retraining-jobs", {
      method: "POST",
      body: JSON.stringify({ requested_by: "local-admin", reason: "Manual dashboard trigger" }),
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["retraining-jobs"] }),
  });
  const promote = useMutation({
    mutationFn: (jobId: string) => apiFetch(`admin/retraining-jobs/${jobId}/promote`, {
      method: "POST",
      body: JSON.stringify({ requested_by: "local-admin" }),
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["retraining-jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["model"] }),
      ]);
    },
  });

  const anyLoading = results.some((result) => result.isLoading);
  const firstError = results.find((result) => result.error)?.error ?? null;
  const decisions = overview.data?.decisions ?? {};

  return (
    <main className="mx-auto min-h-screen max-w-[1600px] px-4 py-6 md:px-8">
      <header className="mb-6 flex flex-col justify-between gap-4 border-b border-border pb-5 md:flex-row md:items-end">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-primary">
            <ShieldAlert className="h-4 w-4" aria-hidden="true" /> Fraud operations
          </div>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Fraud Command Center</h1>
          <p className="mt-1 text-sm text-muted-foreground">Evidence-backed decisions, investigations, drift and platform health.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-400" aria-hidden="true" />
          <span className="text-xs text-muted-foreground">Live · refreshes every 30 seconds</span>
        </div>
      </header>

      <DataState loading={anyLoading} error={firstError as Error | null} />
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="24 hour summary">
        <MetricCard title="Transactions · 24h" value={number.format(overview.data?.transactions_24h ?? 0)} detail={`${number.format(decisions.APPROVE ?? 0)} automatically approved`} icon={Activity} />
        <MetricCard title="Manual review" value={number.format(decisions.MANUAL_REVIEW ?? 0)} detail="Requires analyst attention" icon={AlertTriangle} />
        <MetricCard title="Blocked" value={number.format(decisions.BLOCK ?? 0)} detail={`${number.format(overview.data?.confirmed_fraud_24h ?? 0)} confirmed fraud labels`} icon={CheckCircle2} />
        <MetricCard title="Confirmed fraud blocked" value={money.format(overview.data?.confirmed_fraud_blocked_amount_24h ?? 0)} detail="Verified labels only — no estimate" icon={Banknote} />
      </section>

      <Tabs defaultValue="overview" className="mt-6">
        <TabsList aria-label="Command center views">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="alerts">Alerts</TabsTrigger>
          <TabsTrigger value="model">Model</TabsTrigger>
          <TabsTrigger value="drift">Drift</TabsTrigger>
          <TabsTrigger value="system">System</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
          <Card>
            <CardHeader><CardTitle>Fraud trend</CardTitle><CardDescription>Hourly decisions over the last 24 hours</CardDescription></CardHeader>
            <CardContent className="h-[320px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trends.data ?? []} margin={{ left: -18, right: 8 }}>
                  <defs><linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="var(--primary)" stopOpacity={0.45} /><stop offset="95%" stopColor="var(--primary)" stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="key" tick={{ fill: "var(--muted-foreground)", fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={32} />
                  <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 10 }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }} />
                  <Area type="monotone" dataKey="blocked" stroke="var(--primary)" fill="url(#riskFill)" strokeWidth={2} />
                  <Area type="monotone" dataKey="review" stroke="var(--warning)" fill="transparent" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Recent transactions</CardTitle><CardDescription>{number.format(transactions.data?.total ?? 0)} matching records</CardDescription></CardHeader>
            <CardContent className="overflow-x-auto p-0">
              <table className="w-full text-left text-sm">
                <thead className="border-y border-border text-xs text-muted-foreground">
                  {table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => <th className="px-4 py-3 font-medium" key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}
                </thead>
                <tbody>{table.getRowModel().rows.map((row) => <tr className="border-b border-border/60" key={row.id}>{row.getVisibleCells().map((cell) => <td className="px-4 py-3" key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="alerts">
          <Card>
            <CardHeader><CardTitle>Analyst queue</CardTitle><CardDescription>Resolve cases to create delayed ground-truth labels.</CardDescription></CardHeader>
            <CardContent className="space-y-2">
              {(alerts.data ?? []).map((alert) => (
                <article className="grid gap-3 rounded-lg border border-border p-4 md:grid-cols-[1fr_auto] md:items-center" key={alert.alert_id}>
                  <div><div className="flex items-center gap-2"><span className="font-mono text-sm">{alert.transaction_id}</span><Badge tone={alert.severity === "HIGH" ? "danger" : "warning"}>{alert.severity}</Badge><Badge>{alert.status}</Badge></div><p className="mt-1 text-xs text-muted-foreground">Top reason: {alert.explanation?.top_risk_factors?.[0]?.feature ?? "Explanation pending"}</p></div>
                  {alert.status !== "RESOLVED" ? <div className="flex gap-2"><Button disabled={resolveAlert.isPending} onClick={() => resolveAlert.mutate({ alertId: alert.alert_id, resolution: "FRAUD" })}>Confirm fraud</Button><Button className="border border-border bg-transparent text-foreground" disabled={resolveAlert.isPending} onClick={() => resolveAlert.mutate({ alertId: alert.alert_id, resolution: "LEGITIMATE" })}>Mark legitimate</Button></div> : <Badge tone={alert.resolution === "FRAUD" ? "danger" : "success"}>{alert.resolution}</Badge>}
                </article>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="model" className="grid gap-4 lg:grid-cols-3">
          {[['Precision', performance.data?.precision], ['Recall', performance.data?.recall], ['F1', performance.data?.f1], ['PR-AUC', performance.data?.pr_auc], ['ROC-AUC', performance.data?.roc_auc], ['Calibration · Brier', performance.data?.brier_score]].map(([label, value]) => <Card key={String(label)}><CardHeader><CardTitle>{label}</CardTitle></CardHeader><CardContent><p className="font-mono text-2xl">{typeof value === "number" ? percent.format(value) : "—"}</p></CardContent></Card>)}
          <Card className="lg:col-span-3"><CardHeader><CardTitle>Active model</CardTitle><CardDescription>{model.data?.model_version ?? "Unknown"}</CardDescription></CardHeader><CardContent className="flex flex-wrap gap-3"><Badge>Review ≥ {model.data?.review_threshold ?? "—"}</Badge><Badge tone="danger">Block ≥ {model.data?.block_threshold ?? "—"}</Badge><Badge tone={performance.data?.status === "available" ? "success" : "warning"}>{performance.data?.labeled_transactions ?? 0} labels · {performance.data?.status ?? "loading"}</Badge><Badge>{performanceHistory.data?.[0]?.degradation_detected ? "Performance degraded" : "No delayed-performance trigger"}</Badge></CardContent></Card>
          <Card className="lg:col-span-3"><CardHeader><CardTitle>Retraining lifecycle</CardTitle><CardDescription>Labels affect monitoring immediately; retraining creates a challenger and never promotes it automatically.</CardDescription></CardHeader><CardContent className="space-y-3"><Button disabled={requestRetraining.isPending || retrainingJobs.data?.some((job) => job.status === "QUEUED" || job.status === "RUNNING")} onClick={() => requestRetraining.mutate()}><RefreshCw className="mr-2 h-4 w-4" />Queue manual retraining</Button>{(retrainingJobs.data ?? []).slice(0, 5).map((job) => <article className="flex flex-col justify-between gap-2 rounded-lg border border-border p-3 md:flex-row md:items-center" key={job.job_id}><div><p className="font-mono text-xs">{job.job_id}</p><p className="text-xs text-muted-foreground">{job.trigger_type} · champion {job.champion_version}</p></div><div className="flex items-center gap-2"><Badge tone={job.status === "FAILED" ? "danger" : job.status === "COMPLETED" || job.status === "PROMOTED" ? "success" : "warning"}>{job.status}</Badge>{job.status === "COMPLETED" && job.promotion_recommended ? <Button disabled={promote.isPending} onClick={() => promote.mutate(job.job_id)}>Promote challenger</Button> : null}</div></article>)}</CardContent></Card>
        </TabsContent>

        <TabsContent value="drift">
          <Card><CardHeader><CardTitle>Drift history</CardTitle><CardDescription>Feature and segment reports by model version. A retraining trigger requires two consecutive breached windows.</CardDescription></CardHeader><CardContent className="space-y-2">{(drift.data?.items ?? []).map((report) => <article className="flex flex-col justify-between gap-2 rounded-lg border border-border p-4 md:flex-row md:items-center" key={report.report_id}><div><p className="font-mono text-sm">{report.model_version}</p><p className="text-xs text-muted-foreground">{report.segment} · {new Date(report.window_end).toLocaleString()}</p></div><Badge tone={report.drift_detected ? "danger" : "success"}>{report.drift_detected ? "Threshold breached" : "Stable"}</Badge></article>)}{drift.data?.items.length === 0 ? <p className="text-sm text-muted-foreground">No drift reports yet. The monitor needs at least 100 observations.</p> : null}</CardContent></Card>
        </TabsContent>

        <TabsContent value="system" className="grid gap-4 lg:grid-cols-3">
          <MetricCard title="API" value={firstError ? "Degraded" : "Healthy"} detail="BFF to FastAPI connectivity" icon={Gauge} />
          <MetricCard title="Model" value={model.data?.bootstrap_model ? "Bootstrap" : "Registered"} detail={model.data?.model_version ?? "Awaiting model metadata"} icon={ShieldAlert} />
          <MetricCard title="Data freshness" value={overview.data?.as_of ? new Date(overview.data.as_of).toLocaleTimeString() : "—"} detail="Last analytics snapshot" icon={Activity} />
          <Card className="lg:col-span-3"><CardHeader><CardTitle>Operational telemetry</CardTitle><CardDescription>p50/p95/p99, RPS, error rate, consumer lag, outbox age and worker throughput are sourced from Prometheus/Grafana. This view remains truthful when no samples are available.</CardDescription></CardHeader></Card>
        </TabsContent>
      </Tabs>
    </main>
  );
}
