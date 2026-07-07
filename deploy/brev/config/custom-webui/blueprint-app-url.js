function currentLocation() {
  return window.location;
}

function normalizeAppSlug(appSlug) {
  return String(appSlug || "").trim().toLowerCase();
}

function normalizeHostname(hostname) {
  return String(hostname || "").trim().toLowerCase();
}

function isLocalhost(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1" || hostname === "[::1]";
}

function buildSiblingAppHostname(appSlug, hostname) {
  var labels = hostname.split(".");
  var appLabel = labels[0] || "";
  var separatorIndex = appLabel.indexOf("-");

  if (separatorIndex < 1 || separatorIndex === appLabel.length - 1) {
    return "";
  }

  labels[0] = appSlug + "-" + appLabel.slice(separatorIndex + 1);

  return labels.join(".");
}

function sourceBlueprintAppLinks() {
  return Array.prototype.filter.call(
    document.querySelectorAll("a[data-blueprint-app-slug]"),
    function (link) {
      return !link.closest(".maiw-header-apps");
    }
  );
}

function blueprintAppsFromDashboard() {
  var seen = {};
  var apps = [];

  sourceBlueprintAppLinks().forEach(function (link) {
    var slug = normalizeAppSlug(link.dataset.blueprintAppSlug);
    var title = String(link.textContent || "").trim() || slug;

    if (!slug || seen[slug]) {
      return;
    }

    seen[slug] = true;
    apps.push({ slug: slug, title: title });
  });

  return apps;
}

export function buildBlueprintAppUrl(appSlug, locationOverride) {
  var slug = normalizeAppSlug(appSlug);
  var location = locationOverride || currentLocation();
  var hostname = normalizeHostname(location.hostname);
  var protocol = location.protocol || "https:";

  if (!slug) {
    return "";
  }

  if (isLocalhost(hostname)) {
    return location.origin || protocol + "//" + hostname;
  }

  var siblingHostname = buildSiblingAppHostname(slug, hostname);

  if (!siblingHostname) {
    return "";
  }

  return protocol + "//" + siblingHostname;
}

function updateBlueprintAppLinks(root) {
  var scope = root || document;

  scope.querySelectorAll("a[data-blueprint-app-slug]").forEach(function (link) {
    var url = buildBlueprintAppUrl(link.dataset.blueprintAppSlug);

    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.onclick = function (event) {
      if (event) {
        event.preventDefault();
      }

      return openBlueprintApp(link);
    };

    if (!url) {
      link.setAttribute("aria-disabled", "true");
      link.href = "#";
      return;
    }

    link.href = url;
    link.removeAttribute("aria-disabled");
  });
}

function directHeaderChild(element, header) {
  var child = element;

  while (child && child.parentElement !== header) {
    child = child.parentElement;
  }

  return child && child.parentElement === header ? child : null;
}

function headerAppInsertBefore(header) {
  var title = header.querySelector(".logo-and-title") || header.querySelector("h1");
  var titleChild = title && directHeaderChild(title, header);

  return titleChild ? titleChild.nextSibling : null;
}

function renderHeaderBlueprintAppLinks() {
  var header = document.querySelector("header");
  var apps = blueprintAppsFromDashboard();
  var container = header && header.querySelector(".maiw-header-apps");
  var signature = apps.map(function (app) {
    return app.slug + ":" + app.title;
  }).join("|");

  if (!header) {
    return;
  }

  if (!apps.length) {
    if (container) {
      container.remove();
    }

    return;
  }

  if (!container) {
    container = document.createElement("nav");
    container.className = "maiw-header-apps";
    container.setAttribute("aria-label", "Blueprint apps");
  }

  var insertBefore = headerAppInsertBefore(header);

  if (container.parentElement !== header || container !== insertBefore) {
    header.insertBefore(container, insertBefore);
  }

  if (container.dataset.appsSignature !== signature) {
    container.dataset.appsSignature = signature;
    container.textContent = "";

    apps.forEach(function (app) {
      var link = document.createElement("a");
      var label = document.createElement("span");
      var icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      var box = document.createElementNS("http://www.w3.org/2000/svg", "path");
      var arrow = document.createElementNS("http://www.w3.org/2000/svg", "path");

      link.className = "maiw-header-app-link";
      link.dataset.blueprintAppSlug = app.slug;
      label.className = "maiw-header-app-label";
      label.textContent = app.title;

      icon.classList.add("maiw-header-app-icon");
      icon.setAttribute("aria-hidden", "true");
      icon.setAttribute("viewBox", "0 0 24 24");
      icon.setAttribute("focusable", "false");
      box.setAttribute("d", "M10 6H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4");
      arrow.setAttribute("d", "M14 4h6v6M12 12 20 4");
      icon.appendChild(box);
      icon.appendChild(arrow);

      link.appendChild(label);
      link.appendChild(icon);
      container.appendChild(link);
    });
  }

  updateBlueprintAppLinks(container);
}

function openBlueprintApp(link) {
  var url = buildBlueprintAppUrl(link && link.dataset && link.dataset.blueprintAppSlug);

  if (!url) {
    return false;
  }

  window.open(url, "_blank", "noopener,noreferrer");
  return false;
}

export default function exposeBlueprintAppUrl() {
  window.maiw = window.maiw || {};
  window.maiw.buildBlueprintAppUrl = buildBlueprintAppUrl;
  window.maiw.openBlueprintApp = openBlueprintApp;

  if (window.__maiwBlueprintAppUrlStarted) {
    updateBlueprintAppLinks();
    return;
  }

  window.__maiwBlueprintAppUrlStarted = true;

  function start() {
    updateBlueprintAppLinks();
    renderHeaderBlueprintAppLinks();

    var observer = new MutationObserver(function () {
      updateBlueprintAppLinks();
      renderHeaderBlueprintAppLinks();
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  if (document.body) {
    start();
  } else {
    window.addEventListener("DOMContentLoaded", start, { once: true });
  }
}
