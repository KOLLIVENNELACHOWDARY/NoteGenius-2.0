// Shared behaviour: typeset formulas, busy buttons, copy, print, filter, auto-submit.
(function () {
  // Typeset formulas. If KaTeX cannot read one, show the original text in plain type (never a red error).
  function fitTex(el) {
    var box = el.closest(".feq, .cardtext, .sentence") || el.parentElement;
    if (!box || el.dataset.display !== "1") return;
    el.style.fontSize = "";
    var room = box.clientWidth - 4, need = el.scrollWidth;
    if (room > 0 && need > room) el.style.fontSize = Math.max(0.6, room / need * 0.96).toFixed(3) + "em";
  }
  window.renderTex = function (root) {
    (root || document).querySelectorAll(".tex[data-tex]").forEach(function (el) {
      var tex = el.getAttribute("data-tex");
      if (!tex || !window.katex) return;
      if (!el.dataset.done) {
        var original = el.textContent;
        try {
          window.katex.render(tex, el, { throwOnError: true, displayMode: el.dataset.display === "1", strict: "ignore", errorColor: "inherit" });
          el.dataset.done = "1";
        } catch (e) {
          el.dataset.done = "plain";
          el.textContent = original;
          el.classList.add("tex-plain");
        }
      }
      if (el.dataset.done === "1") fitTex(el);
    });
  };
  window.addEventListener("resize", function () { window.renderTex(); });
  document.addEventListener("DOMContentLoaded", function () { window.renderTex(); });
  window.addEventListener("load", function () { window.renderTex(); });

  // Show a busy label while a slow form is processed. A disabled button is not sent with the form,
  // so the clicked button's name/value is copied into a hidden field first (otherwise "Start quiz" posts nothing).
  document.querySelectorAll("form[data-busy]").forEach(function (form) {
    form.addEventListener("submit", function (ev) {
      var button = ev.submitter || form.querySelector("button[type=submit]");
      if (!button) return;
      if (button.name) {
        var hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = button.name;
        hidden.value = button.value;
        form.appendChild(hidden);
      }
      setTimeout(function () {
        button.dataset.label = button.textContent;
        button.textContent = form.dataset.busy;
        button.disabled = true;
        form.querySelectorAll("button[type=submit]").forEach(function (b) { if (b !== button) b.disabled = true; });
      }, 0);
    });
  });
  window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[data-busy] button[type=submit]").forEach(function (b) {
      if (b.dataset.label) b.textContent = b.dataset.label;
      b.disabled = false;
    });
  });

  document.querySelectorAll("[data-print]").forEach(function (b) {
    b.addEventListener("click", function () { window.print(); });
  });
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var text = b.getAttribute("data-copy");
      var done = function () { var old = b.textContent; b.textContent = "Copied"; setTimeout(function () { b.textContent = old; }, 1200); };
      if (navigator.clipboard) { navigator.clipboard.writeText(text).then(done, function () {}); }
    });
  });
  document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });
  document.querySelectorAll("input[data-filter]").forEach(function (input) {
    var items = document.querySelectorAll(input.getAttribute("data-filter"));
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      items.forEach(function (it) { it.hidden = q && it.textContent.toLowerCase().indexOf(q) === -1; });
    });
  });
})();
