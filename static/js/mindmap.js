// Interactive mind map: fit to screen, zoom, drag to pan, open/close branches, focus on one section.
(function () {
  var view = document.getElementById("mm-viewport");
  if (!view) return;
  var sizer = document.getElementById("mm-sizer"), canvas = document.getElementById("mm-canvas");
  var scale = 1, userZoomed = false;

  function apply() {
    canvas.style.transform = "scale(" + scale + ")";
    sizer.style.width = Math.ceil(canvas.scrollWidth * scale) + "px";
    sizer.style.height = Math.ceil(canvas.scrollHeight * scale) + "px";
  }
  function fit() {
    canvas.style.transform = "none";
    var w = canvas.scrollWidth, h = canvas.scrollHeight;
    var s = Math.min(1, (view.clientWidth - 28) / w, (view.clientHeight - 28) / h);
    scale = Math.max(0.28, s);
    userZoomed = false;
    apply();
    view.scrollLeft = 0; view.scrollTop = 0;
    // centre a map that is smaller than the box
    sizer.style.marginLeft = Math.max(0, (view.clientWidth - 28 - canvas.scrollWidth * scale) / 2) + "px";
    sizer.style.marginTop = Math.max(0, (view.clientHeight - 28 - canvas.scrollHeight * scale) / 2) + "px";
    return h;
  }
  function zoom(f) {
    var cx = (view.scrollLeft + view.clientWidth / 2) / scale, cy = (view.scrollTop + view.clientHeight / 2) / scale;
    scale = Math.min(2, Math.max(0.25, scale * f));
    userZoomed = true;
    sizer.style.marginLeft = sizer.style.marginTop = "0px";
    apply();
    view.scrollLeft = cx * scale - view.clientWidth / 2;
    view.scrollTop = cy * scale - view.clientHeight / 2;
  }
  function refit() { if (!userZoomed) fit(); else { sizer.style.marginLeft = sizer.style.marginTop = "0px"; apply(); } }

  // open / close a section
  view.addEventListener("click", function (e) {
    var t = e.target.closest(".mm-section");
    if (!t || dragged) return;
    var li = t.parentElement;
    if (!li.querySelector(":scope > ul")) return;
    li.classList.toggle("collapsed");
    var b = t.querySelector(".mm-toggle");
    if (b) b.setAttribute("aria-expanded", li.classList.contains("collapsed") ? "false" : "true");
    refit();
  });

  document.querySelectorAll("[data-act]").forEach(function (b) {
    b.addEventListener("click", function () {
      var a = b.getAttribute("data-act");
      if (a === "fit") fit();
      else if (a === "in") zoom(1.2);
      else if (a === "out") zoom(1 / 1.2);
      else if (a === "expand" || a === "collapse") {
        view.querySelectorAll(".mm-section").forEach(function (s) {
          var li = s.parentElement;
          if (!li.querySelector(":scope > ul")) return;
          li.classList.toggle("collapsed", a === "collapse");
          var t = s.querySelector(".mm-toggle");
          if (t) t.setAttribute("aria-expanded", a === "collapse" ? "false" : "true");
        });
        refit();
      } else if (a === "full") {
        var el = view;
        if (document.fullscreenElement) document.exitFullscreen();
        else if (el.requestFullscreen) el.requestFullscreen();
      }
    });
  });

  // focus on one main section
  var branches = view.querySelectorAll(".mm-branches > .mm-li");
  document.querySelectorAll(".mm-chips [data-branch]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var which = chip.getAttribute("data-branch");
      document.querySelectorAll(".mm-chips .chip").forEach(function (c) { c.classList.toggle("on", c === chip); });
      branches.forEach(function (li, i) { li.hidden = which !== "all" && String(i) !== which; });
      view.querySelector(".mm-branches").classList.toggle("solo", which !== "all");
      fit();
    });
  });

  // drag to pan
  var dragging = false, dragged = false, sx = 0, sy = 0, sl = 0, st = 0;
  view.addEventListener("pointerdown", function (e) {
    if (e.target.closest("button")) return;
    dragging = true; dragged = false; sx = e.clientX; sy = e.clientY; sl = view.scrollLeft; st = view.scrollTop;
  });
  window.addEventListener("pointermove", function (e) {
    if (!dragging) return;
    var dx = e.clientX - sx, dy = e.clientY - sy;
    if (Math.abs(dx) + Math.abs(dy) > 4) { dragged = true; view.classList.add("grabbing"); }
    if (dragged) { view.scrollLeft = sl - dx; view.scrollTop = st - dy; }
  });
  window.addEventListener("pointerup", function () {
    dragging = false; view.classList.remove("grabbing");
    setTimeout(function () { dragged = false; }, 0);
  });
  view.addEventListener("wheel", function (e) {
    if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1); }
  }, { passive: false });
  view.addEventListener("keydown", function (e) {
    if (e.key === "+" || e.key === "=") zoom(1.2);
    else if (e.key === "-") zoom(1 / 1.2);
    else if (e.key === "0") fit();
  });

  window.addEventListener("resize", refit);
  window.addEventListener("load", function () { if (window.renderTex) window.renderTex(view); fit(); });
  document.addEventListener("fullscreenchange", function () { setTimeout(refit, 50); });
  fit();
})();
