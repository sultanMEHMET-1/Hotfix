/**
 * The Mender mark: a wand with three mending stitches and a spark, drawn from the original artwork.
 * The wand takes the text color, so it reads on both papers. The spark stays the wet-ink amber.
 * Strokes are a little heavier than the artwork so the mark holds up at header size, but light enough to keep the stitches apart.
 */
export default function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="400 400 1130 1130"
      fill="none"
      strokeWidth={28}
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
    >
      <g stroke="currentColor">
        <path d="M485 1445 1383 547" />
        <path d="M587 1297 633 1343M543 1340 590 1386M500 1385 546 1431" />
        <path d="M929 982A40 40 0 0 1 982 929M1003 950A40 40 0 0 1 950 1003" />
        <path d="M441 1474 455 1488" />
      </g>
      <path d="M1326 444 1385 505M1485 447 1428 504M1428 548 1487 606" stroke="rgb(var(--color-warning))" />
    </svg>
  );
}
