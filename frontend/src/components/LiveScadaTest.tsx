import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  getLiveScadaExperimentStatus,
  getLatestLiveScadaSession,
  runLiveScadaSession,
} from "../services/api";
import type {
  LiveScadaExperimentStatus,
  LiveScadaTestSession,
} from "../types/liveScadaExperiment";


export default function LiveScadaTest() {
  const [status, setStatus] = useState<LiveScadaExperimentStatus | null>(null);
  const [session, setSession] = useState<LiveScadaTestSession | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      const experimentStatus = await getLiveScadaExperimentStatus();
      setStatus(experimentStatus);
      if (experimentStatus.latest_session_id) {
        setSession(await getLatestLiveScadaSession());
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Experiment unavailable");
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const next = await runLiveScadaSession();
      setSession(next);
      setStatus(await getLiveScadaExperimentStatus());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Session failed");
    } finally {
      setBusy(false);
    }
  }

  const evidence = useMemo(
    () =>
      Object.fromEntries(
        (session?.source.field_evidence ?? []).map((item) => [item.field, item]),
      ),
    [session],
  );
  const forecast =
    session?.forecasts.length ? session.forecasts : session?.reference_forecasts ?? [];

  return (
    <section className="grid h-full min-h-0 w-full min-w-0 gap-3 overflow-auto xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.5fr)]">
      <div className="space-y-3">
        <div className="rounded-xl border border-amber-400/35 bg-amber-500/8 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-amber-300">
                Live SCADA Test
              </p>
              <h2 className="mt-1 text-lg font-semibold text-white">
                Static snapshot experiment
              </h2>
            </div>
            <button
              type="button"
              onClick={() => void run()}
              disabled={busy || !status?.configured_source}
              className="rounded-lg border border-cyan-400/40 bg-cyan-500/15 px-4 py-2 text-xs font-semibold text-cyan-100 disabled:opacity-40"
            >
              {busy ? "Processing..." : "Run snapshot"}
            </button>
          </div>
          <p className="mt-3 text-sm text-amber-100">
            EXPERIMENTAL, READ-ONLY DECISION SUPPORT. This is not a live SCADA
            stream and cannot issue control commands.
          </p>
          <p className="mt-2 break-all text-xs text-slate-400">
            {status?.message ?? "Checking configuration..."}
          </p>
          {error ? <p className="mt-2 text-sm text-rose-300">{error}</p> : null}
        </div>

        {session ? (
          <>
            <Panel title="Snapshot provenance">
              <Row label="Source" value={session.source.source_filename} />
              <Row
                label="Available through"
                value={formatTime(session.source.latest_valid_timestamp)}
              />
              <Row label="Weather fetched" value={formatTime(session.weather.fetched_at)} />
              <Row
                label="Freshness"
                value={`${session.processing_metadata.freshness_status ?? "STATIC"} · ${formatAge(session.processing_metadata.snapshot_age_seconds)}`}
              />
              <Row
                label="Model"
                value={`${session.model.model_version ?? "Unavailable"} · ${session.model.status}`}
              />
              <Row
                label="Records"
                value={`${session.source.cleaned_record_count}/${session.source.raw_record_count} accepted`}
              />
              <Row
                label="Source hash"
                value={session.source.source_file_hash.slice(0, 16)}
              />
            </Panel>
            <Panel title="Data quality">
              <Row label="Malformed" value={String(session.source.malformed_record_count)} />
              <Row label="Duplicates" value={String(session.source.duplicate_record_count)} />
              <Row label="Future records" value={String(session.source.future_record_count)} />
              <Row
                label="Missing"
                value={session.source.missing_required_variables.join(", ") || "None"}
              />
            </Panel>
          </>
        ) : null}
      </div>

      <div className="space-y-3">
        {session ? (
          <>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
              <Metric label="Demand" evidence={evidence.current_demand_mw} />
              <Metric label="TRA" evidence={evidence.generation_tra_mw} />
              <Metric label="Corrected spin" evidence={evidence.spinning_reserve_mw} />
              <Metric label="TA / available" evidence={evidence.available_capacity_ta_mw} />
              <Metric label="SCADA temperature" evidence={evidence.temperature_c} />
            </div>
            <Panel title="Observed / forecast boundary">
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                <Badge text={`Observed through ${formatTime(session.source.latest_valid_timestamp)}`} />
                <Badge text={`Weather: ${session.weather.post_boundary_weather_source ?? "unavailable"}`} />
                <Badge text={session.forecasts.length ? "Frozen model inference" : "Reference only"} />
              </div>
              <div className="grid gap-2 md:grid-cols-3">
                {forecast.map((point) => {
                  const risk = session.risk.find(
                    (item) => item.horizon_hours === point.horizon_hours,
                  );
                  return (
                    <div
                      key={point.horizon_hours}
                      className="rounded-lg border border-slate-700 bg-slate-950/65 p-3"
                    >
                      <p className="text-xs uppercase tracking-wider text-slate-400">
                        +{point.horizon_hours} hour
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-cyan-100">
                        {point.forecast_demand_mw.toFixed(1)} MW
                      </p>
                      <p className="mt-1 text-xs text-slate-400">
                        {formatTime(point.forecast_timestamp)}
                      </p>
                      <p className="mt-2 text-xs text-amber-200">
                        Generation need:{" "}
                        {risk?.generation_need_probability == null
                          ? "Unavailable"
                          : `${(risk.generation_need_probability * 100).toFixed(1)}%`}
                      </p>
                    </div>
                  );
                })}
              </div>
            </Panel>
            <Panel title="Validation and interpretation">
              <ul className="space-y-2 text-sm text-slate-300">
                {session.validation_warnings.map((warning) => (
                  <li key={warning} className="rounded-lg bg-slate-950/55 px-3 py-2">
                    {warning}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-slate-500">
                A static snapshot tests model behavior, not forecast accuracy.
                Later actual SCADA values are required for comparison.
              </p>
            </Panel>
          </>
        ) : (
          <div className="flex h-full min-h-64 items-center justify-center rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center text-slate-400">
            {busy ? "Loading experiment..." : "Configure the source and run a snapshot session."}
          </div>
        )}
      </div>
    </section>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/65 p-4">
      <h3 className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-cyan-300">
        {title}
      </h3>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[8rem_minmax(0,1fr)] gap-2 border-b border-slate-800 py-2 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="min-w-0 break-words text-right text-slate-200">{value}</span>
    </div>
  );
}

function Metric({
  label,
  evidence,
}: {
  label: string;
  evidence?: { cleaned_value?: number | null; engineering_unit?: string | null; status: string };
}) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-900/65 p-3 text-center">
      <p className="text-[10px] uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-2 text-lg font-semibold text-white">
        {evidence?.cleaned_value == null
          ? "Unavailable"
          : `${evidence.cleaned_value.toFixed(1)} ${evidence.engineering_unit ?? ""}`}
      </p>
      <p className="mt-1 text-[10px] text-slate-500">{evidence?.status ?? "MISSING"}</p>
    </div>
  );
}

function Badge({ text }: { text: string }) {
  return (
    <span className="rounded-full border border-cyan-400/25 bg-cyan-500/10 px-3 py-1 text-cyan-100">
      {text}
    </span>
  );
}

function formatTime(value?: string | null): string {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat("en-TT", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Port_of_Spain",
  }).format(new Date(value));
}

function formatAge(value?: number): string {
  if (value == null) return "Unknown age";
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  return `${hours}h ${minutes}m old`;
}
