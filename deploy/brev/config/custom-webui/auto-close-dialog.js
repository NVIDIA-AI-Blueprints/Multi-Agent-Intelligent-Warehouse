export default function startAutoCloseDialog() {
  var dashboardPath = "/";

  function onExecutionFinished(event) {
    var entry = event && event.payload && event.payload.logEntry;
    if (!entry) {
      return;
    }

    var expectedPath = "/logs/" + entry.executionTrackingId;
    if (window.location.pathname !== expectedPath) {
      return;
    }

    var succeeded = entry.exitCode === 0 && !entry.timedOut && !entry.blocked;
    if (!succeeded) {
      return;
    }

    window.setTimeout(function () {
      window.location.assign(dashboardPath);
    }, 800);
  }

  window.addEventListener("EventExecutionFinished", onExecutionFinished);
}
