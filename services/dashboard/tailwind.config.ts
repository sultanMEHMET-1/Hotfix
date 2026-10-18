import type { Config } from "tailwindcss";

// Printed lab ledger: vellum paper, hard ink rules, one ink accent. Color carries meaning only
// (litmus green = committed or fast, wet-ink amber = the agent at work, oxblood = failed or struck).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ground: "rgb(var(--color-ground) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        "surface-subtle": "rgb(var(--color-surface-subtle) / <alpha-value>)",
        line: "rgb(var(--color-line) / <alpha-value>)",
        border: "rgb(var(--color-ink) / 0.12)",
        "border-strong": "rgb(var(--color-ink) / 0.2)",
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        "ink-muted": "rgb(var(--color-ink-muted) / <alpha-value>)",
        "ink-faint": "rgb(var(--color-ink-faint) / <alpha-value>)",
        success: "rgb(var(--color-success) / <alpha-value>)",
        "success-bg": "rgb(var(--color-success-bg) / <alpha-value>)",
        warning: "rgb(var(--color-warning) / <alpha-value>)",
        "warning-bg": "rgb(var(--color-warning-bg) / <alpha-value>)",
        danger: "rgb(var(--color-danger) / <alpha-value>)",
        "danger-bg": "rgb(var(--color-danger-bg) / <alpha-value>)",
      },
      fontFamily: {
        display: ["Instrument Sans", "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ["Space Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        xs: "14px",
        sm: "15px",
        base: "17px",
        lg: "22px",
        xl: "34px",
        "2xl": "52px",
        hero: ["clamp(4.5rem, 12vw, 8.5rem)", { lineHeight: "0.9", letterSpacing: "-0.03em" }],
      },
      borderRadius: { panel: "2px" },
      boxShadow: {
        print: "4px 4px 0 rgb(var(--color-shadow))",
        "print-sm": "3px 3px 0 rgb(var(--color-shadow))",
      },
    },
  },
  plugins: [],
} satisfies Config;
