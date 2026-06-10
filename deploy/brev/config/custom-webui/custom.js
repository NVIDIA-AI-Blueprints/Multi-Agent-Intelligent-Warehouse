(function () {
  import("/custom-webui/auto-close-dialog.js")
    .then(function (autoCloseDialog) {
      autoCloseDialog.default();
    })
    .catch(function (error) {
      console.error("Failed to load OliveTin auto-close dialog behavior", error);
    });

  import("/custom-webui/particles.js")
    .then(function (particles) {
      particles.default();
    })
    .catch(function (error) {
      console.error("Failed to load OliveTin particles background", error);
    });

  import("/custom-webui/content-click-scroll-top.js")
    .then(function (contentClickScrollTop) {
      contentClickScrollTop.default();
    })
    .catch(function (error) {
      console.error("Failed to load OliveTin content click scroll behavior", error);
    });
})();
