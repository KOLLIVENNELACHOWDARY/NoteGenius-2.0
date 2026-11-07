// Audio overview: the browser reads the conversation aloud with two different voices (no server work needed).
(function () {
  var play = document.getElementById("play"), stop = document.getElementById("stop");
  if (!play) return;
  var synth = window.speechSynthesis, turns = Array.prototype.slice.call(document.querySelectorAll(".turn"));
  if (!synth || !window.SpeechSynthesisUtterance) { play.disabled = true; document.getElementById("nosupport").hidden = false; return; }
  var running = false, index = 0;

  function voices() {
    var all = synth.getVoices().filter(function (v) { return /^en/i.test(v.lang); });
    if (!all.length) all = synth.getVoices();
    var female = all.filter(function (v) { return /female|zira|samantha|aria|jenny|susan|google uk english female|karen|moira/i.test(v.name); });
    var male = all.filter(function (v) { return /male|david|mark|daniel|guy|google uk english male|alex|fred/i.test(v.name) && !/female/i.test(v.name); });
    return { a: female[0] || all[0], b: male[0] || all[1] || all[0] };
  }
  function clear() { turns.forEach(function (t) { t.classList.remove("now"); }); }
  function finish() { running = false; clear(); play.textContent = "▶ Listen in your browser"; stop.hidden = true; }
  function speak() {
    if (!running || index >= turns.length) { finish(); return; }
    var el = turns[index], v = voices(), u = new SpeechSynthesisUtterance(el.querySelector(".say").textContent);
    var isA = el.getAttribute("data-who") === "A";
    if (isA ? v.a : v.b) u.voice = isA ? v.a : v.b;
    u.pitch = isA ? 1.15 : 0.8;
    u.rate = parseFloat(document.getElementById("rate").value) || 1;
    clear(); el.classList.add("now"); el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    u.onend = function () { index += 1; speak(); };
    u.onerror = function () { finish(); };
    synth.speak(u);
  }
  play.addEventListener("click", function () {
    if (running) { synth.cancel(); finish(); return; }
    synth.cancel(); running = true; index = 0; play.textContent = "Playing..."; stop.hidden = false; speak();
  });
  stop.addEventListener("click", function () { synth.cancel(); finish(); });
  window.addEventListener("beforeunload", function () { synth.cancel(); });
})();
