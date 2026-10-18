(
    <div className="[font-synthesis:none] wrap-anywhere text-xs leading-[16px] flex overflow-clip w-[1400px] h-fit flex-col p-[32px] gap-[32px] bg-surface antialiased">
      <div className="flex flex-col gap-[14px]">
        <div className="font-sans text-[13px] inline-block font-[700] leading-[16px] text-ink">
          Status pill
        </div>
        <div className="flex items-center flex-wrap gap-[16px]">
          <div className="flex items-center py-[6px] px-[14px] rounded-[999px] gap-[8px] bg-surface-muted border border-solid border-border">
            <div className="w-[8px] h-[8px] rounded-[50%] shrink-0 bg-ink-muted" />
            <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-ink-muted">
              Idle
            </div>
          </div>
          <div className="flex items-center py-[6px] px-[14px] rounded-[999px] gap-[8px] [background-color:var(--color-ok-bg)] border border-solid border-ok">
            <div className="w-[8px] h-[8px] rounded-[50%] shrink-0 bg-ok" />
            <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-ok">
              Fast Path · Cached Selector
            </div>
          </div>
          <div className="flex items-center py-[6px] px-[14px] rounded-[999px] gap-[8px] [box-shadow:#D9770626_0px_0px_0px_4px] bg-heal-bg border border-solid border-heal">
            <div className="w-[8px] h-[8px] rounded-[50%] shrink-0 bg-heal" />
            <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-heal">
              Self-Healing Loop · Agent Re-indexing
            </div>
          </div>
          <div className="flex items-center py-[6px] px-[14px] rounded-[999px] gap-[8px] [background-color:var(--color-ok-bg)] border border-solid border-ok">
            <div className="w-[8px] h-[8px] rounded-[50%] shrink-0 bg-ok" />
            <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-ok">
              Healed · Selector Patched
            </div>
            <div className="font-sans inline-block py-[2px] px-[6px] rounded-[999px] bg-heal">
              <div className="inline-block font-sans text-[10px] tracking-[0.04em] uppercase font-[700] leading-[12px] text-surface">
                Healed
              </div>
            </div>
          </div>
          <div className="flex items-center py-[6px] px-[14px] rounded-[999px] gap-[8px] [background-color:var(--color-fail-bg)] border border-solid border-fail">
            <div className="w-[8px] h-[8px] rounded-[50%] shrink-0 bg-fail" />
            <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-fail">
              Recovery failed · rolled back
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-[14px]">
        <div className="font-sans text-[13px] inline-block font-[700] leading-[16px] text-ink">
          Trigger button
        </div>
        <div className="flex items-center gap-[16px]">
          <div className="flex flex-col items-start gap-[6px]">
            <div className="font-sans inline-block py-[10px] px-[18px] rounded-sm bg-ink">
              <div className="inline-block font-sans text-sm font-[600] leading-[18px] text-surface">
                Trigger Workflow
              </div>
            </div>
            <div className="font-sans text-[11px] inline-block leading-[14px] text-ink-muted">
              Default
            </div>
          </div>
          <div className="flex flex-col items-start gap-[6px]">
            <div className="font-sans inline-block py-[10px] px-[18px] rounded-sm bg-[#2A2B2F]">
              <div className="inline-block font-sans text-sm font-[600] leading-[18px] text-surface">
                Trigger Workflow
              </div>
            </div>
            <div className="font-sans text-[11px] inline-block leading-[14px] text-ink-muted">
              Hover
            </div>
          </div>
          <div className="flex flex-col items-start gap-[6px]">
            <div className="font-sans opacity-60 inline-block py-[10px] px-[18px] rounded-sm bg-ink">
              <div className="inline-block font-sans text-sm font-[600] leading-[18px] text-surface">
                Triggering…
              </div>
            </div>
            <div className="font-sans text-[11px] inline-block leading-[14px] text-ink-muted">
              Loading
            </div>
          </div>
          <div className="flex flex-col items-start gap-[6px]">
            <div className="font-sans inline-block py-[10px] px-[18px] rounded-sm bg-surface-muted border border-solid border-border">
              <div className="inline-block font-sans text-sm font-[600] leading-[18px] text-ink-muted">
                Trigger Workflow
              </div>
            </div>
            <div className="font-sans text-[11px] inline-block leading-[14px] text-ink-muted">
              Disabled
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-[14px]">
        <div className="font-sans text-[13px] inline-block font-[700] leading-[16px] text-ink">
          Path label
        </div>
        <div className="flex items-center gap-[24px]">
          <div className="font-mono text-[13px] inline-block font-[500] leading-[16px] text-ink-muted">
            Deterministic Playwright
          </div>
          <div className="font-mono text-[13px] inline-block font-[500] leading-[16px] text-heal">
            Browser Use Agent Engaged
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-[14px]">
        <div className="font-sans text-[13px] inline-block font-[700] leading-[16px] text-ink">
          Mocks toggle &amp; mock scenario picker
        </div>
        <div className="flex items-center gap-[24px]">
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
          <div className="flex items-center p-[4px] rounded-sm gap-[4px] bg-surface-muted border border-solid border-border">
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
      </div>
      <div className="flex flex-col gap-[14px]">
        <div className="font-sans text-[13px] inline-block font-[700] leading-[16px] text-ink">
          Benchmark card
        </div>
        <div className="flex items-start gap-[16px]">
          <div className="flex flex-col w-[280px] p-[16px] rounded-md gap-[10px] shrink-0 bg-surface-muted border border-solid border-border">
            <div className="font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[600] leading-[14px] text-ink-muted">
              Execution time
            </div>
            <div className="flex items-baseline gap-[8px]">
              <div className="font-mono text-xl inline-block font-[600] leading-[34px] text-ink">
                125
              </div>
              <div className="font-mono text-[13px] inline-block leading-[16px] text-ink-muted">
                ms
              </div>
            </div>
          </div>
          <div className="flex flex-col w-[280px] p-[16px] rounded-md gap-[10px] shrink-0 bg-surface-muted border border-solid border-border">
            <div className="font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[600] leading-[14px] text-ink-muted">
              Cost
            </div>
            <div className="flex items-baseline gap-[8px]">
              <div className="font-mono text-[24px] inline-block font-[600] italic leading-[30px] text-ink-muted">
                Unknown
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-[14px]">
        <div className="font-sans text-[13px] inline-block font-[700] leading-[16px] text-ink">
          Sentry button
        </div>
        <div className="flex items-center gap-[16px]">
          <div className="py-[6px] px-[12px] rounded-sm border border-solid border-ink">
            <div className="font-sans text-xs inline-block font-[600] leading-[16px] text-ink">
              Open Sentry trace ↗
            </div>
          </div>
          <div className="flex flex-col items-start gap-[4px]">
            <div className="opacity-50 py-[6px] px-[12px] rounded-sm border border-solid border-border">
              <div className="font-sans text-xs inline-block font-[600] leading-[16px] text-ink-muted">
                Open Sentry trace ↗
              </div>
            </div>
            <div className="font-sans text-[11px] inline-block leading-[14px] text-ink-muted">
              Sentry not configured
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-[14px]">
        <div className="font-sans text-[13px] inline-block font-[700] leading-[16px] text-ink">
          Run log row
        </div>
        <div className="flex flex-col w-[640px] rounded-md overflow-clip border border-solid border-border">
          <div className="flex items-center py-[10px] px-[16px] border-b border-b-solid border-b-border">
            <div className="w-[140px] shrink-0 font-mono text-[13px] inline-block leading-[16px] text-ink">
              14:02:11
            </div>
            <div className="w-[120px] shrink-0 flex items-center gap-[6px]">
              <div className="w-[6px] h-[6px] rounded-[50%] shrink-0 bg-ok" />
              <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-ok">
                success
              </div>
            </div>
            <div className="w-[120px] shrink-0 font-mono text-[13px] inline-block leading-[16px] text-ink">
              125ms
            </div>
            <div className="grow basis-[0%] font-mono text-[13px] inline-block leading-[16px] text-ink">
              $0.0000
            </div>
          </div>
          <div className="flex items-center py-[10px] px-[16px] border-b border-b-solid border-b-border">
            <div className="w-[140px] shrink-0 font-mono text-[13px] inline-block leading-[16px] text-ink">
              14:03:42
            </div>
            <div className="w-[120px] shrink-0 flex items-center gap-[6px]">
              <div className="w-[6px] h-[6px] rounded-[50%] shrink-0 bg-heal" />
              <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-heal">
                healed
              </div>
            </div>
            <div className="w-[120px] shrink-0 font-mono text-[13px] inline-block leading-[16px] text-ink">
              4,200ms
            </div>
            <div className="grow basis-[0%] font-mono text-[13px] inline-block leading-[16px] text-ink">
              $0.0020
            </div>
          </div>
          <div className="flex items-center py-[10px] px-[16px]">
            <div className="w-[140px] shrink-0 font-mono text-[13px] inline-block leading-[16px] text-ink">
              14:05:09
            </div>
            <div className="w-[120px] shrink-0 flex items-center gap-[6px]">
              <div className="w-[6px] h-[6px] rounded-[50%] shrink-0 bg-fail" />
              <div className="font-sans text-[13px] inline-block font-[600] leading-[16px] text-fail">
                failed
              </div>
            </div>
            <div className="w-[120px] shrink-0 font-mono text-[13px] inline-block leading-[16px] text-ink">
              4,200ms
            </div>
            <div className="grow basis-[0%] font-mono text-[13px] inline-block italic leading-[16px] text-ink-muted">
              Unknown
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-[14px]">
        <div className="font-sans text-[13px] inline-block font-[700] leading-[16px] text-ink">
          Error banner
        </div>
        <div className="flex items-start w-[640px] py-[14px] px-[18px] rounded-md gap-[12px] [background-color:var(--color-fail-bg)] border border-solid border-fail">
          <div className="font-mono shrink-0 inline-block py-[2px] px-[8px] rounded-[4px] bg-surface">
            <div className="inline-block font-mono text-[11px] font-[700] leading-[14px] text-fail">
              canary_mismatch
            </div>
          </div>
          <div className="font-sans text-[13px] inline-block font-[500] leading-[16px] text-fail">
            Canary output did not match; the baseline was restored as version 4.
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-[14px]">
        <div className="font-sans text-[13px] inline-block font-[700] leading-[16px] text-ink">
          Heal record row
        </div>
        <div className="flex items-start gap-[16px]">
          <div className="flex flex-col w-[360px] p-[16px] rounded-md gap-[10px] shrink-0 bg-surface border border-solid border-border">
            <div className="flex items-center justify-between">
              <div className="font-mono text-sm inline-block font-[600] leading-[18px] text-ink">
                input_permit_id
              </div>
              <div className="py-[3px] px-[10px] rounded-[999px] [background-color:var(--color-ok-bg)] border border-solid border-ok">
                <div className="font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[700] leading-[14px] text-ok">
                  committed
                </div>
              </div>
            </div>
            <div className="flex gap-[10px]">
              <div className="grow basis-[0%] py-[8px] px-[10px] rounded-sm [background-color:var(--color-diff-old-bg)]">
                <div className="font-mono text-xs inline-block leading-[16px] text-diff-old-fg">
                  #permit-id
                </div>
              </div>
              <div className="grow basis-[0%] py-[8px] px-[10px] rounded-sm [background-color:var(--color-diff-new-bg)]">
                <div className="font-mono text-xs inline-block leading-[16px] text-diff-new-fg">
                  [data-testid='permit-id']
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-col w-[360px] p-[16px] rounded-md gap-[10px] shrink-0 bg-surface border border-solid border-border">
            <div className="flex items-center justify-between">
              <div className="font-mono text-sm inline-block font-[600] leading-[18px] text-ink">
                submit_button
              </div>
              <div className="py-[3px] px-[10px] rounded-[999px] [background-color:var(--color-fail-bg)] border border-solid border-fail">
                <div className="font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[700] leading-[14px] text-fail">
                  rolled back
                </div>
              </div>
            </div>
            <div className="flex gap-[10px]">
              <div className="grow basis-[0%] py-[8px] px-[10px] rounded-sm [background-color:var(--color-diff-old-bg)]">
                <div className="font-mono text-xs inline-block leading-[16px] text-diff-old-fg">
                  #submit-btn
                </div>
              </div>
              <div className="grow basis-[0%] opacity-45 py-[8px] px-[10px] rounded-sm [background-color:var(--color-diff-new-bg)]">
                <div className="font-mono text-xs inline-block leading-[16px] [text-underline-position:from-font] [text-decoration:line-through_1px] text-diff-new-fg">
                  [data-action='lookup']
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-col w-[360px] p-[16px] rounded-md gap-[10px] shrink-0 bg-surface border border-solid border-border">
            <div className="flex items-center justify-between">
              <div className="font-mono text-sm inline-block font-[600] leading-[18px] text-ink">
                confirm_checkbox
              </div>
              <div className="py-[3px] px-[10px] rounded-[999px] bg-surface-muted border border-solid border-border">
                <div className="font-sans text-[11px] uppercase tracking-[0.04em] inline-block font-[700] leading-[14px] text-ink-muted">
                  rejected
                </div>
              </div>
            </div>
            <div className="flex gap-[10px]">
              <div className="grow basis-[0%] py-[8px] px-[10px] rounded-sm [background-color:var(--color-diff-old-bg)]">
                <div className="font-mono text-xs inline-block leading-[16px] text-diff-old-fg">
                  #confirm
                </div>
              </div>
              <div className="grow basis-[0%] opacity-60 py-[8px] px-[10px] rounded-sm bg-surface-muted">
                <div className="font-mono text-xs inline-block leading-[16px] [text-underline-position:from-font] [text-decoration:line-through_1px] text-ink-muted">
                  [data-testid='confirm']
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
