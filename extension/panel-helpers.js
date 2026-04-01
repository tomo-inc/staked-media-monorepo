(function (globalRoot, factory) {
  const api = factory();
  globalRoot.StakedMediaPanelHelpers = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function deriveConnectionIndicator({ health, latencyMs, healthState }) {
    if (healthState === "ready" && health?.status === "ok") {
      return {
        className: "smc-status-dot smc-dot-ok",
        title: latencyMs != null ? `Connected ${latencyMs}ms` : "Connected",
        latencyText: latencyMs != null ? `${latencyMs}ms` : ""
      };
    }

    if (healthState === "error") {
      return {
        className: "smc-status-dot smc-dot-err",
        title: "Disconnected",
        latencyText: ""
      };
    }

    return {
      className: "smc-status-dot smc-dot-warn",
      title: "Checking...",
      latencyText: "--"
    };
  }

  return {
    deriveConnectionIndicator
  };
});
