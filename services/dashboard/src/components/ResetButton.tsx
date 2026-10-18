import { useState } from "react";
import { resetDemo } from "../api/client";

/** Rehearsal reset: puts the original selectors back so Chaos Mode can break them again. */
export default function ResetButton({ disabled, workflow }: { disabled: boolean; workflow?: string }) {
  const [pending, setPending] = useState(false);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);

  const reset = async () => {
    setPending(true);
    setNote(null);
    try {
      const { version, blocked } = await resetDemo(workflow);
      // The file is restored, but a backend that blocked itself (for example after a failed rollback) stays blocked.
      setNote(blocked
        ? { text: `Selectors restored (v${version}), but the backend is blocked: ${blocked}`, ok: false }
        : { text: `Selectors reset (v${version})`, ok: true });
    } catch (e) {
      setNote({ text: e instanceof Error ? e.message : String(e), ok: false });
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={reset}
        disabled={disabled || pending}
        title="Restore the original selectors on the backend"
        className="min-h-[44px] rounded-panel border-[1.5px] border-ink bg-surface px-4 font-display text-sm transition-colors hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50"
      >
        {pending ? "Resetting" : "Reset selectors"}
      </button>
      {note && (
        <span role="status" className={`text-sm ${note.ok ? "text-ink-muted" : "text-danger"}`}>
          {note.text}
        </span>
      )}
    </div>
  );
}
