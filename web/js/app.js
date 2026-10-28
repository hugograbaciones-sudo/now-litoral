/* NOW LITORAL — lógica del portal (ETAPA 1)
   Lee data/news.json (lo genera el motor de noticias en la ETAPA 2) y data/radios.json.
   No inventa contenido: si no hay datos, lo dice. */
(() => {
  "use strict";

  const CONFIG = {
    // Cuando el motor publique en GitHub Pages, cambiar esta línea por la URL absoluta del news.json.
    NEWS_URL: "data/news.json",
    RADIOS_URL: "data/radios.json",
    REFRESCO_MS: 5 * 60 * 1000,
    ZONA: "America/Argentina/Buenos_Aires",
    PAGINA: 24,
    MOSTRAR_ESPACIOS_PUBLICITARIOS: true,
  };

  const CATEGORIAS = [
    ["ultimas", "Últimas noticias"], ["argentina", "Argentina"], ["entre-rios", "Entre Ríos"],
    ["gualeguaychu", "Gualeguaychú"], ["politica", "Política"], ["economia", "Economía"],
    ["sociedad", "Sociedad"], ["policiales", "Policiales"], ["deportes", "Deportes"],
    ["internacionales", "Internacionales"], ["tecnologia", "Tecnología e IA"],
    ["espectaculos", "Espectáculos"], ["agro", "Agro y producción"],
  ];
  const NOMBRE_CAT = Object.fromEntries(CATEGORIAS);
  const SECCIONES_HOME = [
    ["entre-rios", ""], ["deportes", "bloque--verde"], ["internacionales", "bloque--azul"], ["tecnologia", ""],
  ];

  const estado = { items: [], categoria: "ultimas", medio: "", texto: "", visibles: CONFIG.PAGINA, actualizado: null, fallo: false };

  const $ = (s, r = document) => r.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = (s) => String(s).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

  function urlWeb(u) {
    try { const x = new URL(u); return x.protocol === "https:" || x.protocol === "http:" ? x.href : null; } catch { return null; }
  }
  function urlHttps(u) {
    try { const x = new URL(u); return x.protocol === "https:" ? x.href : null; } catch { return null; }
  }

  /* ---------- Fechas (siempre hora de Argentina) ---------- */
  const fmtFecha = new Intl.DateTimeFormat("es-AR", { timeZone: CONFIG.ZONA, weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const fmtHora = new Intl.DateTimeFormat("es-AR", { timeZone: CONFIG.ZONA, hour: "2-digit", minute: "2-digit", hour12: false });
  const fmtCorta = new Intl.DateTimeFormat("es-AR", { timeZone: CONFIG.ZONA, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });

  function hace(ms) {
    const m = Math.round((Date.now() - ms) / 60000);
    if (m < 1) return "ahora";
    if (m < 60) return `hace ${m} min`;
    const h = Math.floor(m / 60);
    if (h < 24) return `hace ${h} h`;
    return fmtCorta.format(ms);
  }
  function relojear() {
    const ahora = new Date();
    $("#fecha-hora").textContent = `${fmtFecha.format(ahora)} · ${fmtHora.format(ahora)} h (Argentina)`;
  }

  /* ---------- Datos ---------- */
  function normalizar(lista) {
    const vistos = new Set();
    const out = [];
    for (const it of Array.isArray(lista) ? lista : []) {
      const url = urlWeb(it && it.url);
      const titulo = String((it && it.titulo) || "").trim();
      const medio = String((it && it.medio) || "").trim();
      const fecha = Date.parse(it && it.fecha);
      if (!url || !titulo || !medio || Number.isNaN(fecha) || vistos.has(url)) continue;
      vistos.add(url);
      out.push({
        titulo, medio, url, fecha,
        categoria: NOMBRE_CAT[it.categoria] && it.categoria !== "ultimas" ? it.categoria : "argentina",
        categorias: Array.isArray(it.categorias) ? it.categorias.filter((c) => NOMBRE_CAT[c]) : [],
        imagen: urlHttps(it.imagen),
        resumen: String(it.resumen || "").trim().slice(0, 280),
      });
    }
    return out.sort((a, b) => b.fecha - a.fecha);
  }
  const perteneceA = (it, cat) => it.categoria === cat || it.categorias.includes(cat);

  function filtrados() {
    const q = norm(estado.texto.trim());
    return estado.items.filter((it) =>
      (estado.categoria === "ultimas" || perteneceA(it, estado.categoria)) &&
      (!estado.medio || it.medio === estado.medio) &&
      (!q || norm(`${it.titulo} ${it.medio} ${it.resumen}`).includes(q)));
  }

  async function cargar() {
    try {
      const r = await fetch(CONFIG.NEWS_URL, { cache: "no-cache" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      const items = normalizar(d.items);
      estado.items = items;
      estado.actualizado = d.actualizado ? Date.parse(d.actualizado) : null;
      estado.fallo = false;
    } catch (e) {
      estado.fallo = true; // se conserva la última edición válida, si la hay
    }
    render();
  }

  /* ---------- Piezas HTML ---------- */
  function marcador(it) {
    return `<div class="media media--vacio cat-${esc(it.categoria)}" aria-hidden="true"><span>${esc(it.medio.charAt(0).toUpperCase())}</span></div>`;
  }
  function media(it) {
    if (!it.imagen) return marcador(it);
    return `<div class="media"><img src="${esc(it.imagen)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-img></div>`;
  }
  const meta = (it) => `<div class="meta"><span class="chip">${esc(it.medio)}</span><span class="cat">${esc(NOMBRE_CAT[it.categoria])}</span></div>`;
  const hora = (it) => `<time datetime="${new Date(it.fecha).toISOString()}" title="${esc(fmtCorta.format(it.fecha))} h">${esc(hace(it.fecha))} · ${esc(fmtHora.format(it.fecha))} h</time>`;
  const abrir = (it) => `href="${esc(it.url)}" target="_blank" rel="noopener noreferrer"`;

  function tarjeta(it) {
    return `<article class="tarjeta"><a ${abrir(it)} style="display:flex;flex-direction:column;height:100%">
      ${media(it)}
      <div class="tarjeta__cuerpo">${meta(it)}<h3>${esc(it.titulo)}</h3>${it.resumen ? `<p>${esc(it.resumen)}</p>` : ""}${hora(it)}</div>
    </a></article>`;
  }
  function hero(it) {
    return `<a class="hero" ${abrir(it)}>${media(it)}<div class="hero__texto">${meta(it)}<h2>${esc(it.titulo)}</h2>${it.resumen ? `<p>${esc(it.resumen)}</p>` : ""}${hora(it)}</div></a>`;
  }
  function mini(it) {
    return `<a class="mini" ${abrir(it)}>${media(it)}<div>${meta(it)}<h3>${esc(it.titulo)}</h3>${hora(it)}</div></a>`;
  }
  const espacioInline = () => CONFIG.MOSTRAR_ESPACIOS_PUBLICITARIOS
    ? `<div class="publi grilla__publi"><span class="publi__rotulo">Publicidad</span><div class="publi__caja">Espacio publicitario · entre noticias</div></div>` : "";

  /* ---------- Render ---------- */
  function renderMenu() {
    $("#menu").innerHTML = CATEGORIAS.map(([id, nombre]) =>
      `<button type="button" role="tab" data-cat="${id}" aria-selected="${id === estado.categoria}">${esc(nombre)}</button>`).join("");
  }
  function renderMedios() {
    const sel = $("#filtro-medio");
    const medios = [...new Set(estado.items.map((i) => i.medio))].sort((a, b) => a.localeCompare(b, "es"));
    sel.innerHTML = `<option value="">Todos</option>` + medios.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("");
    sel.value = medios.includes(estado.medio) ? estado.medio : "";
    if (sel.value !== estado.medio) estado.medio = "";
  }
  function renderTicker() {
    const ult = estado.items.slice(0, 10);
    const caja = $("#ticker");
    if (!ult.length) { caja.hidden = true; return; }
    const una = ult.map((it) => `<a ${abrir(it)}><small>${esc(it.medio)}</small>${esc(it.titulo)}</a>`).join("");
    $("#ticker-cinta").innerHTML = una + una; // duplicado para el efecto continuo
    caja.hidden = false;
  }

  function renderEstado(hayItems) {
    const el = $("#estado");
    el.className = "estado";
    if (!hayItems) {
      el.className = "estado estado--vacio";
      el.textContent = estado.fallo
        ? "No pudimos cargar las noticias en este momento. Reintentamos automáticamente en unos minutos."
        : "Todavía no hay noticias publicadas. Aparecerán acá apenas el motor de actualización publique la primera edición.";
      return;
    }
    const medios = new Set(estado.items.map((i) => i.medio)).size;
    const cuando = estado.actualizado ? ` · actualizado ${fmtHora.format(estado.actualizado)} h` : "";
    const aviso = estado.fallo ? " · No se pudo actualizar; se muestra la última edición disponible." : "";
    el.textContent = `${estado.items.length} noticias de ${medios} medios${cuando}${aviso}`;
  }

  function render() {
    const hayItems = estado.items.length > 0;
    renderEstado(hayItems);
    renderMedios();
    renderTicker();

    const lista = $("#lista"), dest = $("#destacadas"), filtros = $("#filtros"), mas = $("#mas"), sec = $("#secciones");
    document.querySelectorAll(".publi[data-espacio]").forEach((p) => { p.hidden = !(hayItems && CONFIG.MOSTRAR_ESPACIOS_PUBLICITARIOS); });

    if (!hayItems) {
      lista.innerHTML = ""; dest.hidden = true; filtros.hidden = true; mas.hidden = true; sec.innerHTML = "";
      return;
    }
    filtros.hidden = false;
    $("#titulo-lista").textContent = estado.texto.trim() ? `Resultados para “${estado.texto.trim()}”` : NOMBRE_CAT[estado.categoria];

    const todos = filtrados();
    const esInicio = estado.categoria === "ultimas" && !estado.medio && !estado.texto.trim();
    let resto = todos;

    if (esInicio && todos.length >= 1) {
      const principal = todos.find((i) => i.imagen) || todos[0];
      const laterales = todos.filter((i) => i !== principal).slice(0, 3);
      dest.innerHTML = hero(principal) + `<div class="destacadas__lado">${laterales.map(mini).join("")}</div>`;
      dest.hidden = false;
      const usados = new Set([principal, ...laterales]);
      resto = todos.filter((i) => !usados.has(i));
    } else {
      dest.hidden = true; dest.innerHTML = "";
    }

    if (!todos.length) {
      lista.innerHTML = `<p class="estado estado--vacio">No hay noticias para esa búsqueda o filtro.</p>`;
      mas.hidden = true;
    } else {
      const visibles = resto.slice(0, estado.visibles);
      const piezas = visibles.map(tarjeta);
      if (piezas.length > 6) piezas.splice(6, 0, espacioInline());
      lista.innerHTML = `<div class="grilla">${piezas.join("")}</div>`;
      mas.hidden = resto.length <= estado.visibles;
    }

    if (esInicio) {
      sec.innerHTML = SECCIONES_HOME.map(([cat, clase]) => {
        const del = estado.items.filter((i) => perteneceA(i, cat)).slice(0, 4);
        if (!del.length) return "";
        return `<section class="bloque ${clase}"><h2 class="titulo-seccion">${esc(NOMBRE_CAT[cat])}</h2><div class="grilla">${del.map(tarjeta).join("")}</div></section>`;
      }).join("");
    } else {
      sec.innerHTML = "";
    }
  }

  /* ---------- Eventos ---------- */
  function eventos() {
    $("#menu").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-cat]");
      if (!b) return;
      estado.categoria = b.dataset.cat; estado.visibles = CONFIG.PAGINA;
      renderMenu(); render();
      $("#contenido").scrollIntoView({ block: "start" });
    });
    $("#filtro-medio").addEventListener("change", (e) => { estado.medio = e.target.value; estado.visibles = CONFIG.PAGINA; render(); });
    let t;
    $("#buscar").addEventListener("input", (e) => {
      clearTimeout(t);
      t = setTimeout(() => { estado.texto = e.target.value; estado.visibles = CONFIG.PAGINA; render(); }, 180);
    });
    $("#ver-mas").addEventListener("click", () => { estado.visibles += CONFIG.PAGINA; render(); });
    // Si una imagen remota falla, se reemplaza por el marcador de color (sin romper la tarjeta).
    document.addEventListener("error", (e) => {
      const img = e.target;
      if (!(img instanceof HTMLImageElement) || !img.hasAttribute("data-img")) return;
      const caja = img.closest(".media");
      if (caja) caja.outerHTML = `<div class="media media--vacio" aria-hidden="true"><span>·</span></div>`;
    }, true);
  }

  /* ---------- Tema claro / oscuro ---------- */
  function tema() {
    let guardado = null;
    try { guardado = localStorage.getItem("nl-tema"); } catch { /* sin almacenamiento */ }
    if (guardado === "claro" || guardado === "oscuro") document.documentElement.dataset.tema = guardado;
    $("#tema").addEventListener("click", () => {
      const raiz = document.documentElement;
      const oscuroAhora = raiz.dataset.tema === "oscuro" ||
        (raiz.dataset.tema === "auto" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
      const nuevo = oscuroAhora ? "claro" : "oscuro";
      raiz.dataset.tema = nuevo;
      try { localStorage.setItem("nl-tema", nuevo); } catch { /* sin almacenamiento */ }
    });
  }

  /* ---------- Radio online ---------- */
  async function radio() {
    let lista = [];
    try {
      const r = await fetch(CONFIG.RADIOS_URL, { cache: "no-cache" });
      if (!r.ok) throw new Error();
      const d = await r.json();
      lista = (Array.isArray(d.emisoras) ? d.emisoras : [])
        .filter((e) => e && e.nombre && e.activa !== false && urlHttps(e.stream)) // los streams http no suenan en un sitio https
        .sort((a, b) => (a.orden || 0) - (b.orden || 0));
    } catch { lista = []; }
    if (!lista.length) return; // sin emisoras activas, la barra queda oculta

    const barra = $("#radio"), btn = $("#radio-play"), est = $("#radio-estado"), vol = $("#radio-vol"), sel = $("#radio-sel");
    const audio = new Audio();
    audio.preload = "none";
    audio.volume = Number(vol.value);
    let actual = 0, sonando = false;

    const mostrar = () => {
      const e = lista[actual];
      $("#radio-nombre").textContent = e.nombre;
      const logo = urlHttps(e.logo);
      const im = $("#radio-logo");
      if (logo) { im.src = logo; im.hidden = false; } else { im.hidden = true; }
      est.textContent = e.descripcion ? String(e.descripcion).slice(0, 60) : "Radio online";
    };
    const poner = (txt, play) => {
      est.textContent = txt; sonando = play;
      btn.textContent = play ? "❚❚" : "▶";
      btn.setAttribute("aria-label", play ? "Pausar" : "Reproducir");
    };
    const reproducir = () => {
      audio.src = urlHttps(lista[actual].stream); // reconecta en vivo al reanudar
      poner("Conectando…", true);
      audio.play().catch(() => poner("No se pudo conectar con la emisora", false));
    };
    const parar = () => { audio.pause(); audio.removeAttribute("src"); audio.load(); poner("En pausa", false); };

    btn.addEventListener("click", () => (sonando ? parar() : reproducir()));
    vol.addEventListener("input", () => { audio.volume = Number(vol.value); });
    audio.addEventListener("playing", () => poner("En vivo", true));
    audio.addEventListener("waiting", () => { if (sonando) est.textContent = "Conectando…"; });
    audio.addEventListener("error", () => { if (audio.getAttribute("src")) poner("Emisora no disponible", false); });

    if (lista.length > 1) {
      sel.innerHTML = lista.map((e, i) => `<option value="${i}">${esc(e.nombre)}</option>`).join("");
      sel.hidden = false;
      sel.addEventListener("change", () => {
        const estabaSonando = sonando;
        actual = Number(sel.value); mostrar();
        if (estabaSonando) reproducir(); else poner("Radio online", false);
      });
    }
    mostrar();
    barra.hidden = false;
    document.body.classList.add("con-radio");
  }

  /* ---------- Inicio ---------- */
  function iniciar() {
    tema();
    renderMenu();
    eventos();
    relojear();
    setInterval(relojear, 30000);
    cargar();
    setInterval(() => { if (!document.hidden) cargar(); }, CONFIG.REFRESCO_MS);
    radio();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar); else iniciar();
})();
