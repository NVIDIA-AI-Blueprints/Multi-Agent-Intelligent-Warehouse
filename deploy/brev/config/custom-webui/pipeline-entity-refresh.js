var DASHBOARD_TITLE = "Multi-Agent Intelligent Warehouse Launcher";
var PIPELINE_ROW_TITLE = "Pipeline";
var PIPELINE_BUTTON_SELECTOR = ".pipeline-status-button";

function normalizeSignaturePart(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function signatureFromPipelineButtons(buttons) {
  return Array.prototype.map.call(buttons, function (button) {
    return [
      normalizeSignaturePart(button.textContent),
      normalizeSignaturePart(button.className),
      normalizeSignaturePart(button.getAttribute("href"))
    ].join("::");
  }).join("||");
}

function signatureFromDom() {
  var buttons = document.querySelectorAll(PIPELINE_BUTTON_SELECTOR);

  if (!buttons.length) {
    return "";
  }

  return signatureFromPipelineButtons(buttons);
}

function displayHtmlFromComponent(component) {
  var html = [];

  if (!component) {
    return html;
  }

  if (component.type === "display" && String(component.title || "").indexOf("pipeline-status-button") !== -1) {
    html.push(component.title);
  }

  if (Array.isArray(component.contents)) {
    component.contents.forEach(function (child) {
      html = html.concat(displayHtmlFromComponent(child));
    });
  }

  return html;
}

function pipelineComponentFromDashboard(dashboard) {
  var rows = dashboard && Array.isArray(dashboard.contents) ? dashboard.contents : [];
  var directMatch = rows.find(function (row) {
    return row && row.title === PIPELINE_ROW_TITLE;
  });

  if (directMatch) {
    return directMatch;
  }

  return rows.find(function (row) {
    return displayHtmlFromComponent(row).length > 0;
  });
}

function signatureFromDashboard(dashboard) {
  var pipeline = pipelineComponentFromDashboard(dashboard);
  var html = displayHtmlFromComponent(pipeline);
  var template = document.createElement("template");

  template.innerHTML = html.join("");

  return signatureFromPipelineButtons(template.content.querySelectorAll(PIPELINE_BUTTON_SELECTOR));
}

function currentDashboardTitle() {
  var loadedDashboard = document.body && document.body.getAttribute("loaded-dashboard");
  var rootDashboards = window.initResponse && window.initResponse.rootDashboards;

  if (loadedDashboard && loadedDashboard !== "default" && loadedDashboard !== "error") {
    return loadedDashboard;
  }

  if (Array.isArray(rootDashboards) && rootDashboards.length > 0) {
    return rootDashboards[0];
  }

  return DASHBOARD_TITLE;
}

function dashboardHasPipeline() {
  return document.querySelector(PIPELINE_BUTTON_SELECTOR) !== null;
}

export default function startPipelineEntityRefresh() {
  var lastPipelineSignature = "";
  var comparePending = false;
  var reloading = false;

  function rememberRenderedPipeline() {
    var signature = signatureFromDom();

    if (signature) {
      lastPipelineSignature = signature;
    }
  }

  async function latestPipelineSignature() {
    var response;

    if (!window.client || typeof window.client.getDashboard !== "function") {
      return "";
    }

    response = await window.client.getDashboard({
      title: currentDashboardTitle()
    });

    return signatureFromDashboard(response && response.dashboard);
  }

  async function comparePipelineSignature() {
    var currentSignature;
    var nextSignature;

    comparePending = false;

    if (reloading || !dashboardHasPipeline()) {
      return;
    }

    currentSignature = lastPipelineSignature || signatureFromDom();

    if (!currentSignature) {
      rememberRenderedPipeline();
      return;
    }

    try {
      nextSignature = await latestPipelineSignature();
    } catch (error) {
      console.error("Failed to refresh OliveTin dashboard after entity change", error);
      return;
    }

    if (!nextSignature || nextSignature === currentSignature) {
      lastPipelineSignature = nextSignature || currentSignature;
      return;
    }

    reloading = true;
    lastPipelineSignature = nextSignature;
    window.location.reload();
  }

  function scheduleCompare() {
    if (comparePending || reloading) {
      return;
    }

    comparePending = true;
    window.setTimeout(comparePipelineSignature, 150);
  }

  rememberRenderedPipeline();

  var observer = new MutationObserver(function () {
    rememberRenderedPipeline();
  });

  if (document.body) {
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  window.addEventListener("EventEntityChanged", scheduleCompare);
}
