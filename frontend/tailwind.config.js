/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#16232e", soft: "#3b4a57" },
        muted: "#66768a",
        line: { DEFAULT: "#e3e8ed", strong: "#d3dae1" },
        canvas: "#f4f6f8",
        navy: { DEFAULT: "#0d2630", 2: "#12313d", 3: "#1a3d4a" },
        accent: { DEFAULT: "#0f766e", dark: "#0b5e58", soft: "#eaf5f3", ring: "#99d3cc" },
        danger: { DEFAULT: "#b42318", soft: "#fef3f2", line: "#fecdca" },
        warn: { DEFAULT: "#a15c07", soft: "#fffaeb", line: "#fedf89" },
        good: { DEFAULT: "#067647", soft: "#ecfdf3", line: "#abefc6" },
        info: { DEFAULT: "#175cd3", soft: "#eff8ff", line: "#b2ddff" },
      },
      fontFamily: {
        sans: ['"Inter"', '"Segoe UI"', "system-ui", "-apple-system", "Roboto", "Helvetica", "Arial", "sans-serif"],
        mono: ['"JetBrains Mono"', "Consolas", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.03)",
        pop: "0 12px 32px -8px rgba(16,24,40,.18), 0 4px 8px -4px rgba(16,24,40,.08)",
      },
      borderRadius: { xl: "12px" },
    },
  },
  plugins: [],
};
