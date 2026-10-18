import { useEffect, useRef, useState } from "react";
import type { WorkflowSummary } from "@contracts/api_types";
import { createDraft, deleteWorkflow, keepDraft, type DraftPreview } from "../api/client";
import { useElapsed } from "../hooks/useElapsed";
import { formatDuration, formatUsd } from "../lib/format";
import { isCreated, type PublicSite } from "../lib/workflowLabel";

const SITE_NAME: Record<PublicSite, string> = {
  wikipedia: "Wikipedia", python: "python.org", books: "Books to Scrape", quotes: "Quotes to Scrape",
};
// Sentences that were run for real and built working workflows, so every suggestion is safe to click.
const EXAMPLES: Record<PublicSite, string[]> = {
  wikipedia: [
    "Look up Marie Curie on Wikipedia and tell me the article heading",
    "Search Wikipedia for Mount Everest and read the page heading",
    "Look up Alan Turing on Wikipedia and report the page title",
  ],
  python: [
    "Find the newest Python release on the python.org downloads page",
    "Open the python.org downloads page and report the latest release number",
  ],
  books: [
    "Open the Travel category on books.toscrape.com and report the title and price of the first book",
    "Open the Mystery category and report the price of the first book",
  ],
  quotes: [
    "Click the love tag and report the first quote and its author",
    "Click the inspirational tag and report the first quote",
  ],
};
const LIMIT = 300;

const PRIMARY = "min-h-[48px] rounded-panel border-[1.5px] border-ink bg-ink px-6 font-display text-base text-ground transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50";
const SECONDARY = "min-h-[48px] rounded-panel border-[1.5px] border-ink bg-surface px-6 font-display text-base transition-colors hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50";

function stepSentence(step: DraftPreview["steps"][number]): string {
  const label = step.label ?? "the control";
  return step.action === "input" ? `Types ${step.param ? `{${step.param}}` : "text"} into ${label}` : `Clicks ${label}`;
}

export interface CreateWorkflowProps {
  /** The public site the selected workflow reads. */
  site: PublicSite;
  /** The selected workflow, so a created one can be deleted from here. */
  selectedId: string;
  /** A run is in flight: saving or deleting would change the selected workflow under it, so wait. */
  locked?: boolean;
  onKept: (workflow: WorkflowSummary) => void;
  onDeleted: (id: string) => void;
}

/** Describe a read-only task in a sentence; the backend builds, tests and previews a workflow, and the user keeps or discards it. */
export default function CreateWorkflow({ site, selectedId, locked = false, onKept, onDeleted }: CreateWorkflowProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftPreview | null>(null);
  const controller = useRef<AbortController | null>(null);
  const elapsed = useElapsed(busy);
  // Leaving the page or the site stops waiting for a creation that is no longer wanted.
  useEffect(() => () => controller.current?.abort(), []);

  const create = async () => {
    controller.current?.abort();
    controller.current = new AbortController();
    setBusy(true);
    setError(null);
    setDraft(null);
    try {
      setDraft(await createDraft(site, text, controller.current.signal));
    } catch (e) {
      if ((e as { name?: string })?.name !== "AbortError") setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const keep = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      onKept(await keepDraft(draft));
      setDraft(null);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteWorkflow(selectedId);
      onDeleted(selectedId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="create-title" className="mt-12">
      <h2 id="create-title" className="text-xl">Create a workflow from a sentence</h2>
      <p className="mt-2 max-w-[62ch] text-base text-ink-muted">
        Describe what to read on {SITE_NAME[site]}. Mender builds the workflow, tests it twice on the real site, and shows you what it made.
      </p>

      <div className="mt-5 flex flex-col gap-2" role="group" aria-label="Example sentences that work">
        <span className="text-sm text-ink-muted">Try one that is known to work</span>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES[site].map((example) => (
            <button
              key={example}
              type="button"
              disabled={busy}
              onClick={() => setText(example)}
              className="min-h-[44px] rounded-panel border-[1.5px] border-ink bg-surface px-3 py-2 text-left text-sm transition-colors hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50"
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      <label htmlFor="create-request" className="mt-6 block text-sm text-ink-muted">What should it read?</label>
      <textarea
        id="create-request"
        value={text}
        maxLength={LIMIT}
        rows={2}
        disabled={busy}
        onChange={(e) => setText(e.target.value)}
        placeholder="Or describe your own"
        className="mt-2 block w-full resize-y rounded-panel border-[1.5px] border-ink bg-surface px-4 py-3 text-base text-ink placeholder:text-ink-faint disabled:opacity-60"
      />
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-3">
        <button type="button" onClick={create} disabled={busy || text.trim().length < 5} className={PRIMARY}>
          {busy && !draft ? "Creating" : "Create workflow"}
        </button>
        <span className="font-mono text-sm tabular-nums text-ink-muted" aria-live="off">{text.length} / {LIMIT}</span>
        {busy && !draft && (
          <span role="status" className="flex items-baseline gap-3 text-warning">
            <span className="min-w-[4.5rem] font-mono text-lg tabular-nums">{`${(elapsed / 1000).toFixed(1)} s`}</span>
            <span className="text-base">Reading the page and testing the result</span>
          </span>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-5 rounded-panel border-[1.5px] border-danger bg-danger-bg px-5 py-4 text-base text-danger">{error}</p>
      )}

      {draft && (
        <div className="mt-8 border-y-[1.5px] border-ink" aria-label="Preview of the new workflow">
          <div className="grid gap-x-8 gap-y-5 py-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="flex flex-col gap-3">
              <h3 className="text-lg">{draft.goal}</h3>
              <ol className="m-0 flex list-none flex-col gap-1.5 p-0 text-base">
                {draft.steps.map((step, i) => (
                  <li key={i} className="flex gap-3"><span className="w-5 shrink-0 font-mono text-ink-muted">{i + 1}</span><span>{stepSentence(step)}</span></li>
                ))}
                {draft.outputs.map((o) => (
                  <li key={o.name} className="flex gap-3"><span className="w-5 shrink-0 font-mono text-ink-muted">=</span><span>Reads {o.description || o.name}</span></li>
                ))}
              </ol>
            </div>
            <div className="flex flex-col gap-2">
              <span className="text-sm text-ink-muted">Sample result for {draft.params.map((p) => `${p.name} = ${p.example}`).join(", ") || "no input"}</span>
              <pre className="m-0 overflow-x-auto rounded-panel border border-border-strong bg-surface p-4 font-mono text-base">{JSON.stringify(draft.sample_output, null, 2)}</pre>
              <span className="text-sm text-ink-muted">
                Built in {formatDuration(draft.duration_ms)} for {draft.cost_usd === null ? "an unknown cost" : formatUsd(draft.cost_usd)}. Tested on two different inputs.
              </span>
            </div>
          </div>
          {draft.warnings.length > 0 && <p className="pb-4 text-sm text-warning">{draft.warnings.join(" ")}</p>}
          <div className="flex flex-wrap gap-3 border-t border-line py-5">
            <button type="button" onClick={keep} disabled={busy || locked} className={PRIMARY}>Save workflow</button>
            <button type="button" onClick={() => setDraft(null)} disabled={busy} className={SECONDARY}>Discard</button>
          </div>
        </div>
      )}

      {isCreated(selectedId) && !draft && (
        <div className="mt-8 flex flex-wrap items-center gap-4 border-t border-line pt-5">
          <span className="text-base text-ink-muted">This workflow was created from a sentence.</span>
          <button type="button" onClick={remove} disabled={busy || locked} className={SECONDARY}>Delete workflow</button>
        </div>
      )}

      <ul className="mt-8 flex list-none flex-col gap-1.5 p-0 text-sm text-ink-muted">
        <li>Reads only. Anything that edits, logs in, buys or posts is refused before the model runs.</li>
        <li>Wikipedia, python.org and two practice sites only. Each creation costs about a cent and takes under a minute.</li>
        <li>Content that changes (news, rankings) can fail the repair check later. A person confirms every preview.</li>
        <li>Pages behind a login or captcha are refused, never bypassed.</li>
      </ul>
    </section>
  );
}
