// Rotina — JS mínimo: relógio do timer, diálogo de parar, chamadas de IA.
(function () {
  "use strict";

  // ---------- relógio do timer
  const relogios = document.querySelectorAll("[data-timer-segundos]");
  if (relogios.length) {
    const base = Date.now();
    const iniciais = Array.from(relogios, (el) => parseInt(el.dataset.timerSegundos, 10) || 0);
    const fmt = (s) => {
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
      return (h ? h + ":" : "") + String(m).padStart(h ? 2 : 1, "0") + ":" + String(x).padStart(2, "0");
    };
    const tick = () => {
      const passado = Math.floor((Date.now() - base) / 1000);
      relogios.forEach((el, i) => { el.textContent = fmt(iniciais[i] + passado); });
      const t = relogios[0];
      if (t) document.title = "● " + t.textContent + " · " + (t.dataset.tarefa || "Rotina");
    };
    tick();
    setInterval(tick, 1000);
  }

  // ---------- diálogo de parar timer
  const dlgParar = document.getElementById("dlg-parar");
  document.querySelectorAll("[data-abrir-parar]").forEach((b) =>
    b.addEventListener("click", () => {
      dlgParar.showModal();
      const campo = dlgParar.querySelector("input[name=proximo_passo]");
      if (campo) setTimeout(() => campo.focus(), 30);
    }));
  document.querySelectorAll("[data-fechar]").forEach((b) =>
    b.addEventListener("click", () => b.closest("dialog").close()));

  // ---------- IA
  const dlgIA = document.getElementById("dlg-ia");
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function markdownLeve(texto) {
    const linhas = esc(texto).split(/\r?\n/);
    let html = "", lista = false;
    const inline = (l) => l.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
    for (let l of linhas) {
      const item = l.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
      if (item) {
        if (!lista) { html += "<ul>"; lista = true; }
        html += "<li>" + inline(item[1]) + "</li>";
        continue;
      }
      if (lista) { html += "</ul>"; lista = false; }
      const tit = l.match(/^#{1,4}\s+(.*)$/);
      if (tit) { html += "<p><strong>" + inline(tit[1]) + "</strong></p>"; continue; }
      if (l.trim()) html += "<p>" + inline(l) + "</p>";
    }
    if (lista) html += "</ul>";
    return html;
  }

  function rodape(j, refazer) {
    const origem = j.cache
      ? "da memória · gerada em " + esc(j.criada_em) + " · sem gastar tokens"
      : "gerada agora por IA";
    return '<p class="ia-rotulo">' + origem + " — só sugestão, nada foi alterado" +
      (refazer ? ' · <a href="#" data-ia-refazer>refazer</a>' : "") + "</p>";
  }

  function mostrar(destino, j, refazer) {
    destino.innerHTML = j.ok
      ? markdownLeve(j.texto) + rodape(j, !!refazer)
      : '<p class="perigo">' + esc(j.erro || "Erro na IA.") + "</p>";
    const link = destino.querySelector("[data-ia-refazer]");
    if (link && refazer) link.addEventListener("click", (e) => { e.preventDefault(); refazer(); });
  }

  async function perguntarIA(url, corpo, titulo, alvo, forcar) {
    const destino = alvo || dlgIA.querySelector(".ia-texto");
    if (!alvo) {
      dlgIA.querySelector(".ia-titulo").textContent = titulo || "Assistente";
      if (!dlgIA.open) dlgIA.showModal();
    }
    destino.innerHTML = '<p class="ia-carregando">' + (forcar ? "gerando de novo…" : "pensando…") + "</p>";
    const envio = Object.assign({}, corpo || {}, forcar ? { refazer: true } : {});
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(envio),
      });
      const j = await r.json();
      mostrar(destino, j, () => perguntarIA(url, corpo, titulo, alvo, true));
    } catch (e) {
      destino.innerHTML = '<p class="perigo">Não consegui falar com o servidor local.</p>';
    }
  }

  // Ao abrir a tela Hoje: mostra a última resposta ainda válida, sem chamar a IA.
  const caixaHoje = document.querySelector("[data-ia-caixa][data-ia-memoria]");
  if (caixaHoje) {
    fetch("/ia/memoria?modo=primeiro").then((r) => r.json()).then((j) => {
      const alvo = caixaHoje.querySelector(".ia-texto");
      if (j.ok && !alvo.innerHTML.trim())
        mostrar(alvo, j, () => perguntarIA("/ia/perguntar", { modo: "primeiro" }, null, alvo, true));
    }).catch(() => {});
  }

  const testar = document.querySelector("[data-ia-testar]");
  if (testar) testar.addEventListener("click", () =>
    perguntarIA("/ia/testar", {}, null, document.querySelector("[data-ia-resultado-teste]")));

  // ---------- confirmações
  document.querySelectorAll("form[data-confirmar]").forEach((f) =>
    f.addEventListener("submit", (e) => { if (!confirm(f.dataset.confirmar)) e.preventDefault(); }));

  // ---------- filtros que se enviam sozinhos ao trocar o seletor
  document.querySelectorAll("form[data-autoenviar] select").forEach((sel) =>
    sel.addEventListener("change", () => sel.form.submit()));

  // ---------- tooltip dos gráficos (mouse, toque e teclado)
  const tip = document.getElementById("g-tooltip");
  if (tip) {
    const mostrarTip = (alvo, x, y) => {
      tip.textContent = alvo.dataset.tip;
      tip.hidden = false;
      const w = tip.offsetWidth, h = tip.offsetHeight;
      tip.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x - w / 2)) + "px";
      tip.style.top = Math.max(8, y - h - 12) + "px";
    };
    document.querySelectorAll(".g-alvo").forEach((a) => {
      a.setAttribute("tabindex", "0");
      a.addEventListener("mousemove", (e) => mostrarTip(a, e.clientX, e.clientY));
      a.addEventListener("mouseleave", () => { tip.hidden = true; });
      a.addEventListener("focus", () => {
        const r = a.getBoundingClientRect();
        a.classList.add("foco");
        mostrarTip(a, r.left + r.width / 2, r.top + r.height / 2);
      });
      a.addEventListener("blur", () => { a.classList.remove("foco"); tip.hidden = true; });
      a.addEventListener("touchstart", (e) => {
        const t = e.touches[0]; mostrarTip(a, t.clientX, t.clientY);
      }, { passive: true });
    });
    window.addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });
  }

  // ---------- atalho: "/" foca a captura da garagem
  const captura = document.querySelector(".captura input");
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && captura && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      e.preventDefault(); captura.focus();
    }
  });
})();
