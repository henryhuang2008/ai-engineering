/* quiz.js — reusable immediate-feedback quiz widget.
   Usage: <div class="quiz" data-src="quiz-0001.json"></div>
   Or embed: <div class="quiz"><script type="application/json">{...}</script></div>
   JSON format: { "questions": [ { "q": "...", "options": ["a","b","c"], "correct": 1, "explain": "..." } ] }
*/
(function () {
  function render(quizEl, data) {
    var questions = data.questions || [];
    var answered = 0;
    var correctCount = 0;
    var scoreEl = document.createElement("div");
    scoreEl.className = "score";

    questions.forEach(function (q, qi) {
      var block = document.createElement("div");
      block.className = "q-block";

      var qEl = document.createElement("div");
      qEl.className = "q";
      var num = document.createElement("span");
      num.className = "qnum";
      num.textContent = "Q" + (qi + 1);
      qEl.appendChild(num);
      qEl.appendChild(document.createTextNode(q.q));
      block.appendChild(qEl);

      var opts = document.createElement("div");
      opts.className = "options";

      var explain = document.createElement("div");
      explain.className = "explain";
      explain.textContent = q.explain || "";

      var done = false;
      var buttons = [];

      q.options.forEach(function (opt, oi) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = opt;
        btn.addEventListener("click", function () {
          if (done) return;
          done = true;
          answered++;
          var isRight = oi === q.correct;
          if (isRight) correctCount++;
          buttons.forEach(function (b) { b.disabled = true; });
          btn.classList.add(isRight ? "correct" : "wrong");
          if (!isRight && buttons[q.correct]) {
            buttons[q.correct].classList.add("correct");
          }
          explain.classList.add("shown");
          if (answered === questions.length) {
            scoreEl.textContent =
              "Score: " + correctCount + " / " + questions.length +
              (correctCount === questions.length
                ? " — clean sweep."
                : " — revisit the linked sections above, then retry later.");
            scoreEl.classList.add("shown");
          }
        });
        buttons.push(btn);
        opts.appendChild(btn);
      });

      block.appendChild(opts);
      block.appendChild(explain);
      quizEl.appendChild(block);
    });

    quizEl.appendChild(scoreEl);
  }

  function boot() {
    document.querySelectorAll(".quiz").forEach(function (el) {
      var src = el.getAttribute("data-src");
      var inline = el.querySelector('script[type="application/json"]');
      if (inline) {
        try { render(el, JSON.parse(inline.textContent)); } catch (e) { console.error(e); }
      } else if (src) {
        fetch(src).then(function (r) { return r.json(); })
          .then(function (d) { render(el, d); })
          .catch(function (e) { console.error(e); });
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
