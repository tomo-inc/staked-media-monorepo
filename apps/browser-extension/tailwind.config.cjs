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
          primary: "#1d9bf0",
          "primary-content": "#ffffff",
          secondary: "#0f1419",
          "secondary-content": "#f5f8fa",
          accent: "#48d7ee",
          "accent-content": "#082432",
          neutral: "#0f1419",
          "neutral-content": "#f5f8fa",
          "base-100": "#ffffff",
          "base-200": "#f7f9f9",
          "base-300": "#e6ecf0",
          "base-content": "#0f1419",
          info: "#1d9bf0",
          success: "#00ba7c",
          warning: "#ffad1f",
          error: "#f4212e",
          "--rounded-box": "18px",
          "--rounded-btn": "999px",
          "--rounded-badge": "999px",
          "--animation-btn": "0.2s",
          "--animation-input": "0.2s",
          "--btn-text-case": "none",
          "--btn-focus-scale": "0.98",
          "--border-btn": "1px",
          "--tab-border": "2px",
          "--tab-radius": "999px"
        }
      },
      {
        foxspark_coinbase_dark: {
          primary: "#1d9bf0",
          "primary-content": "#ffffff",
          secondary: "#15202b",
          "secondary-content": "#e7e9ea",
          accent: "#7ab8ff",
          "accent-content": "#052640",
          neutral: "#15202b",
          "neutral-content": "#e7e9ea",
          "base-100": "#15202b",
          "base-200": "#1e2732",
          "base-300": "#2f3336",
          "base-content": "#e7e9ea",
          info: "#1d9bf0",
          success: "#00ba7c",
          warning: "#ffad1f",
          error: "#ff6b6b",
          "--rounded-box": "18px",
          "--rounded-btn": "999px",
          "--rounded-badge": "999px",
          "--animation-btn": "0.2s",
          "--animation-input": "0.2s",
          "--btn-text-case": "none",
          "--btn-focus-scale": "0.98",
          "--border-btn": "1px",
          "--tab-border": "2px",
          "--tab-radius": "999px"
        }
      }
    ]
  },
  theme: {
    extend: {}
  }
};
