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
  theme: {
    extend: {}
  }
};
