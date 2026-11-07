// Flashcard study mode: flip, mark known / review again, review loop, filters. Data comes from #deck-data.
(function () {
  var data = JSON.parse(document.getElementById("deck-data").textContent);
  var cardEl = document.getElementById("card"), status = document.getElementById("status"), bar = document.getElementById("bar");
  var done = document.getElementById("done"), rate = document.getElementById("rate");
  var queue = [], known = 0, seen = 0, total = 0, flipped = false, current = null, missedIds = {};

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function tex(node, latex, fallback) {
    var s = el("span", "tex", fallback);
    if (latex) { s.setAttribute("data-tex", latex); s.setAttribute("data-display", "1"); }
    node.appendChild(s);
  }
  function active() {
    var on = {};
    document.querySelectorAll("#type-chips input:checked").forEach(function (c) { on[c.value] = true; });
    return data.filter(function (c) { return on[c.type]; });
  }
  function shuffle(a) {
    for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; }
    return a;
  }
  function start(randomise) {
    var cards = active().slice();
    queue = randomise ? shuffle(cards) : cards;
    total = queue.length; known = 0; seen = 0; missedIds = {};
    done.hidden = true; cardEl.hidden = false; rate.hidden = false;
    next();
  }
  function paint() {
    cardEl.textContent = "";
    cardEl.className = "bigcard" + (flipped ? " back" : "");
    var meta = el("span", "tag", (flipped ? "Answer" : "Question") + (current.section ? "  ·  " + current.section : ""));
    cardEl.appendChild(meta);
    var body = el("div", "cardbody");
    if (!flipped) {
      body.appendChild(el("p", "cardtext", current.front.text));
      if (current.front.formula_tex) tex(body, current.front.formula_tex, "");
    } else {
      if (current.back.tex) {
        tex(body, current.back.tex, current.back.text);
        if (current.back.vars && current.back.vars.length) {
          var dl = el("dl", "vars");
          current.back.vars.forEach(function (v) {
            var row = el("div"), dt = el("dt"), dd = el("dd", null, v[1]);
            var s = el("span", "tex", v[0]); s.setAttribute("data-tex", v[0]); dt.appendChild(s);
            row.appendChild(dt); row.appendChild(dd); dl.appendChild(row);
          });
          body.appendChild(dl);
        }
      } else {
        current.back.text.split("\n").forEach(function (line) { body.appendChild(el("p", "cardtext", line)); });
      }
    }
    cardEl.appendChild(body);
    cardEl.appendChild(el("span", "hint", flipped ? "" : "Press to flip"));
    window.renderTex(cardEl);
  }
  function progress() {
    var left = queue.length;
    status.textContent = total ? "Known " + known + " of " + total + "  ·  " + left + " left in this round" : "No cards selected";
    bar.style.width = total ? Math.round(100 * known / total) + "%" : "0%";
  }
  function next() {
    flipped = false;
    progress();
    if (!queue.length) { finish(); return; }
    current = queue[0];
    paint();
  }
  function finish() {
    cardEl.hidden = true; rate.hidden = true; done.hidden = false;
    done.textContent = "";
    done.appendChild(el("h2", null, total ? "Round complete" : "Pick at least one card type"));
    if (total) {
      var again = Object.keys(missedIds).length;
      done.appendChild(el("p", null, "You know all " + total + " cards. " + (again ? again + " needed a second look." : "None needed a second look.")));
    }
  }
  function flip() { if (!current) return; flipped = !flipped; paint(); }
  function mark(good) {
    if (!current || !queue.length) return;
    var c = queue.shift();
    if (good) { known++; } else { missedIds[c.id] = true; var pos = Math.min(queue.length, 3 + Math.floor(Math.random() * 3)); queue.splice(pos, 0, c); }
    next();
  }
  cardEl.addEventListener("click", flip);
  document.getElementById("know").addEventListener("click", function () { mark(true); });
  document.getElementById("again").addEventListener("click", function () { mark(false); });
  document.getElementById("shuffle").addEventListener("click", function () { start(true); });
  document.querySelectorAll("#type-chips input").forEach(function (c) { c.addEventListener("change", function () { start(false); }); });
  document.addEventListener("keydown", function (e) {
    var t = e.target.tagName;
    if (t === "INPUT" || t === "TEXTAREA" || t === "SELECT") return;
    if (e.key === " " || e.key === "Enter") { if (document.activeElement !== cardEl) { e.preventDefault(); flip(); } }
    else if (e.key === "ArrowRight") mark(true);
    else if (e.key === "ArrowLeft") mark(false);
  });
  start(false);
})();
