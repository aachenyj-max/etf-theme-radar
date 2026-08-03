import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F7F6F2",
        paper: "#FCFCFA",
        ink: "#10273D",
        muted: "#647583",
        line: "#DDE3E3",
        signal: "#1A7162",
        amber: "#B8802E"
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,39,61,.04), 0 10px 30px rgba(16,39,61,.035)"
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.35rem"
      }
    }
  },
  plugins: []
};

export default config;
