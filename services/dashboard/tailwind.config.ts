import type { Config } from "tailwindcss";

// Theme values are filled in from design/tokens.json once the Paper export lands.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
