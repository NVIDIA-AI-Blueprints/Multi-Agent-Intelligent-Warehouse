export default function startLinkifyDescriptions() {
  if (window.__maiwLinkifyDescriptionsStarted) {
    return;
  }

  window.__maiwLinkifyDescriptionsStarted = true;

  var urlPattern = /https:\/\/[^\s<>"')]+/g;

  function linkifyElement(element) {
    if (!element || element.dataset.maiwLinkified === "true") {
      return;
    }

    var text = element.textContent || "";
    var matches = Array.from(text.matchAll(urlPattern));
    if (matches.length === 0) {
      return;
    }

    var fragment = document.createDocumentFragment();
    var cursor = 0;

    matches.forEach(function (match) {
      var url = match[0];
      var index = match.index || 0;

      if (index > cursor) {
        fragment.appendChild(document.createTextNode(text.slice(cursor, index)));
      }

      var link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = url;
      fragment.appendChild(link);

      cursor = index + url.length;
    });

    if (cursor < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(cursor)));
    }

    element.replaceChildren(fragment);
    element.dataset.maiwLinkified = "true";
  }

  function linkifyDescriptions() {
    document.querySelectorAll(".argument-description").forEach(linkifyElement);
  }

  linkifyDescriptions();

  var observer = new MutationObserver(linkifyDescriptions);
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
}
