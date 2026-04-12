module.exports = {
  content: [
    "./public/*.html",
    "./src/entries/**/*.{ts,js}",
    "./src/scripts/**/*.{ts,js}",
    "./src/styles/**/*.css"
  ],
  corePlugins: {
    preflight: false
  },
  plugins: [require("daisyui")],
  daisyui: {
    logs: false,
    darkTheme: "foxspark_coinbase_dark",
    themes: [
      {
        foxspark_coinbase: {
          primary: "#3c84ff",
          "primary-content": "#ffffff",
          secondary: "#0e2340",
          "secondary-content": "#e9f2ff",
          accent: "#48d7ee",
          "accent-content": "#06202b",
          neutral: "#0e2340",
          "neutral-content": "#e9f2ff",
          "base-100": "#ffffff",
          "base-200": "#f4f9ff",
          "base-300": "#d7e5fb",
          "base-content": "#0e2340",
          info: "#3c84ff",
          success: "#16a34a",
          warning: "#c57a08",
          error: "#dc2626",
          "--rounded-box": "16px",
          "--rounded-btn": "8px",
          "--rounded-badge": "999px",
          "--animation-btn": "0.2s",
          "--animation-input": "0.2s",
          "--btn-text-case": "none",
          "--btn-focus-scale": "0.98",
          "--border-btn": "1px",
          "--tab-border": "2px",
          "--tab-radius": "8px"
        }
      },
      {
        foxspark_coinbase_dark: {
          primary: "#7ab8ff",
          "primary-content": "#071a33",
          secondary: "#0b2141",
          "secondary-content": "#e9f2ff",
          accent: "#48d7ee",
          "accent-content": "#06202b",
          neutral: "#0b2141",
          "neutral-content": "#e9f2ff",
          "base-100": "#0c203c",
          "base-200": "#102845",
          "base-300": "#1f3a5d",
          "base-content": "#e9f2ff",
          info: "#7ab8ff",
          success: "#3fd58b",
          warning: "#f3b34c",
          error: "#ff8080",
          "--rounded-box": "16px",
          "--rounded-btn": "8px",
          "--rounded-badge": "999px",
          "--animation-btn": "0.2s",
          "--animation-input": "0.2s",
          "--btn-text-case": "none",
          "--btn-focus-scale": "0.98",
          "--border-btn": "1px",
          "--tab-border": "2px",
          "--tab-radius": "8px"
        }
      }
    ]
  },
  theme: {
    extend: {}
  }
};
