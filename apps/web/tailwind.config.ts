import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "var(--paper)",
        card: "var(--card)",
        ink: "var(--ink)",
        "ink-soft": "var(--ink-soft)",
        rule: "var(--rule)",
        mark: "var(--mark)",
        flag: "var(--flag)",
      },
      fontFamily: {
        document: ["var(--font-document)"],
        ui: ["var(--font-ui)"],
      },
    },
  },
  plugins: [],
} satisfies Config;
