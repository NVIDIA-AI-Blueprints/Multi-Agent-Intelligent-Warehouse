export default function startContentClickScrollTop() {
  if (window.__maiwContentClickScrollTopStarted) {
    return;
  }

  window.__maiwContentClickScrollTopStarted = true;

  function isContentBackgroundClick(event) {
    var target = event.target;
    var content = document.getElementById("content");

    if (!target) {
      return false;
    }

    if (target.closest && target.closest([
      "a",
      "button",
      "input",
      "select",
      "textarea",
      "label",
      "form",
      "section",
      "fieldset",
      "table",
      "pre",
      "code",
      "dialog",
      "header",
      "aside",
      "footer",
      "[role='button']",
      "[role='link']",
      ".button",
      ".action-button",
      ".mre-container"
    ].join(","))) {
      return false;
    }

    if (content && (target === content || target.closest("#content"))) {
      return true;
    }

    return target === document.body || target === document.documentElement;
  }

  function goToDashboard() {
    if (window.location.pathname === "/") {
      return;
    }

    window.location.assign("/");
  }

  function onClick(event) {
    var isBackground = isContentBackgroundClick(event);

    if (!isBackground) {
      return;
    }

    goToDashboard();
  }

  document.addEventListener("click", onClick, true);
}
