import { useState } from "react";
import { resetDemo } from "../api/client";

/** Rehearsal reset: puts the original selectors back so Chaos Mode can break them again. */
export default function ResetButton({ disabled }: { disabled: boolean }) {
  const [pending, setPending] = useState(false);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);

  const reset = async () => {
    setPending(true);
    setNote(null);
    try {
      const { version } = await resetDemo();
      setNote({ text: `Selectors reset (v${version})`, ok: true });
    } catch (e) {
      setNote({ text: e instanceof Error ? e.message : String(e), ok: false });
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={reset}
        disabled={disabled || pending}
        title="Restore the original selectors on the backend"
        className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
      >
        {pending ? "Resetting" : "Reset selectors"}
      </button>
      {note && (
        <span role="status" className={`text-xs ${note.ok ? "text-ink-muted" : "text-danger"}`}>
          {note.text}
        </span>
      )}
    </div>
  );
}
