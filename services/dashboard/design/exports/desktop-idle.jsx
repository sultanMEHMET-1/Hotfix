(
    <div className="[font-synthesis:none] wrap-anywhere text-xs leading-[16px] flex overflow-clip w-[1280px] h-fit flex-col bg-surface antialiased">
      <div className="flex items-center justify-between [width:100%] py-[20px] px-[32px] border-b border-b-solid border-b-border">
        <div className="flex items-center gap-[16px]">
          <div className="font-sans text-lg tracking-[-0.01em] inline-block font-[700] leading-[24px] text-ink">
            Mender
          </div>
          <div className="flex items-center py-[4px] px-[10px] rounded-sm gap-[6px] bg-surface-muted border border-solid border-border">
            <div className="font-mono text-xs inline-block font-[500] leading-[16px] text-ink-muted">
              permit-application
            </div>
          </div>
        </div>
        <div className="flex items-center gap-[8px]">
          <div className="font-sans text-xs inline-block leading-[16px] text-ink-muted">
            Mocks
          </div>
          <div className="w-[32px] h-[18px] flex items-center justify-end p-[2px] rounded-[9px] shrink-0 bg-ink">
            <div className="w-[14px] h-[14px] rounded-[7px] shrink-0 bg-surface" />
          </div>
          <div className="font-mono text-[11px] inline-block font-[600] leading-[14px] text-ink">
            ON
          </div>
        </div>
      </div>
      <div className="flex items-center [width:100%] py-[24px] px-[32px] gap-[16px]">
        <div className="font-sans inline-block py-[10px] px-[18px] rounded-sm bg-ink">
          <div className="inline-block font-sans text-sm font-[600] leading-[18px] text-surface">
            Trigger Workflow
          </div>
        </div>
        <div className="flex items-center py-[6px] px-[14px] rounded-[999px] gap-[8px] bg-surface-muted border border-solid border-border">
          <div className="w-[8px] h-[8px] rounded-[50%] shrink-0 bg-ink-muted" />
          <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-ink-muted">
            Idle
          </div>
        </div>
        <div className="flex items-center ml-auto p-[4px] rounded-sm gap-[4px] bg-surface-muted border border-solid border-border">
          <div className="py-[6px] px-[14px] rounded-sm [box-shadow:#0000000F_0px_1px_2px] bg-surface">
            <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-ink">
              Fast
            </div>
          </div>
          <div className="py-[6px] px-[14px] rounded-sm">
            <div className="font-sans text-[13px] inline-block font-[500] leading-[16px] text-ink-muted">
              Heal
            </div>
          </div>
          <div className="py-[6px] px-[14px] rounded-sm">
            <div className="font-sans text-[13px] inline-block font-[500] leading-[16px] text-ink-muted">
              Rollback
            </div>
          </div>
        </div>
      </div>
      <div className="flex [width:100%] pb-[24px] gap-[20px] px-[32px]">
        <div className="grow basis-[0%] flex flex-col opacity-55 p-[20px] rounded-md gap-[14px] bg-surface-muted border border-solid border-border">
          <div className="font-sans text-xs uppercase tracking-[0.04em] inline-block font-[600] leading-[16px] text-ink-muted">
            Execution time
          </div>
          <div className="flex items-baseline gap-[10px]">
            <div className="font-mono text-2xl inline-block font-[600] leading-[48px] text-ink">
              125
            </div>
            <div className="font-mono text-base inline-block leading-[20px] text-ink-muted">
              ms
            </div>
            <div className="font-sans text-[13px] inline-block leading-[16px] text-ink-muted">
              Deterministic Playwright
            </div>
          </div>
          <div className="flex items-baseline gap-[10px]">
            <div className="font-mono text-lg inline-block font-[500] leading-[24px] text-ink-muted">
              4,200
            </div>
            <div className="font-mono text-[13px] inline-block leading-[16px] text-ink-muted">
              ms
            </div>
            <div className="font-sans text-xs inline-block leading-[16px] text-ink-muted">
              Browser Use Agent (3,100ms agent)
            </div>
          </div>
        </div>
        <div className="grow basis-[0%] flex flex-col opacity-55 p-[20px] rounded-md gap-[14px] bg-surface-muted border border-solid border-border">
          <div className="font-sans text-xs uppercase tracking-[0.04em] inline-block font-[600] leading-[16px] text-ink-muted">
            Cost
          </div>
          <div className="flex items-baseline gap-[10px]">
            <div className="font-mono text-2xl inline-block font-[600] leading-[48px] text-ink">
              $0.0000
            </div>
            <div className="font-sans text-[13px] inline-block leading-[16px] text-ink-muted">
              Cached Run
            </div>
          </div>
          <div className="flex items-baseline gap-[10px]">
            <div className="font-mono text-lg inline-block font-[500] leading-[24px] text-ink-muted">
              $0.0020
            </div>
            <div className="font-sans text-xs inline-block leading-[16px] text-ink-muted">
              Agent Run
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col [width:100%] pb-[24px] gap-[14px] px-[32px]">
        <div className="font-sans text-xs uppercase tracking-[0.04em] inline-block font-[600] leading-[16px] text-ink-muted">
          Latency, last 10 runs
        </div>
        <div className="flex items-center justify-center [width:100%] h-[120px] rounded-md shrink-0 bg-surface-muted border border-dashed border-border">
          <div className="font-sans text-[13px] inline-block leading-[16px] text-ink-muted">
            No runs yet — trigger the workflow to see latency history
          </div>
        </div>
      </div>
      <div className="flex flex-col [width:100%] pb-[24px] gap-[14px] px-[32px]">
        <div className="flex items-center justify-between">
          <div className="font-sans text-xs uppercase tracking-[0.04em] inline-block font-[600] leading-[16px] text-ink-muted">
            Visual Diff Viewer
          </div>
          <div className="flex items-center opacity-50 py-[6px] px-[12px] rounded-sm gap-[6px] border border-solid border-border">
            <div className="font-sans text-xs inline-block font-[600] leading-[16px] text-ink-muted">
              Open Sentry trace ↗
            </div>
          </div>
        </div>
        <div className="flex items-center justify-center [width:100%] h-[140px] rounded-md shrink-0 bg-surface-muted border border-dashed border-border">
          <div className="font-sans text-[13px] inline-block leading-[16px] text-ink-muted">
            No selector changes — the cache is still fresh
          </div>
        </div>
      </div>
      <div className="flex flex-col [width:100%] pb-[32px] gap-[14px] px-[32px]">
        <div className="font-sans text-xs uppercase tracking-[0.04em] inline-block font-[600] leading-[16px] text-ink-muted">
          Run log
        </div>
        <div className="flex flex-col [width:100%] rounded-md overflow-clip border border-solid border-border">
          <div className="flex items-center py-[10px] px-[16px] bg-surface-muted border-b border-b-solid border-b-border">
            <div className="w-[140px] shrink-0 font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[600] leading-[14px] text-ink-muted">
              Time
            </div>
            <div className="w-[120px] shrink-0 font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[600] leading-[14px] text-ink-muted">
              Status
            </div>
            <div className="w-[120px] shrink-0 font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[600] leading-[14px] text-ink-muted">
              Duration
            </div>
            <div className="w-[120px] shrink-0 font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[600] leading-[14px] text-ink-muted">
              Cost
            </div>
            <div className="grow basis-[0%] font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[600] leading-[14px] text-ink-muted">
              Trace ID
            </div>
          </div>
          <div className="flex items-center justify-center py-[28px] px-[16px]">
            <div className="font-sans text-[13px] inline-block leading-[16px] text-ink-muted">
              No runs recorded yet
            </div>
          </div>
        </div>
      </div>
    </div>
  )
