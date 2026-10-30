// NOW LITORAL - https://now-litoral.pages.dev/news.json
// Cloudflare Pages Function. Entrega en JSON las noticias que publica el motor (GitHub Actions),
// sin JavaScript en el navegador y sin iniciar sesion. Solo lee datos publicos: no toca banners,
// radios, usuarios ni credenciales.
//
// Parametros opcionales (para lectores automaticos como ChatGPT):
//   ?categoria=deportes   ?medio=Olé   ?q=boca   ?limit=50   (por defecto 100, maximo 600)

const ORIGEN = "https://hugograbaciones-sudo.github.io/now-litoral/news.json";
const LIMITE_DEFECTO = 100;
const LIMITE_MAX = 600;

const sinTildes = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

function responder(cuerpo, estado = 200, extra = {}) {
  return new Response(JSON.stringify(cuerpo), {
    status: estado,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      // Frescura: el borde guarda la respuesta como maximo 30 s y el navegador siempre revalida.
      "Cache-Control": "public, max-age=0, s-maxage=30, must-revalidate",
      "Access-Control-Allow-Origin": "*",
      "X-Content-Type-Options": "nosniff",
      ...extra,
    },
  });
}

export async function onRequest({ request }) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return responder({ error: "Metodo no permitido" }, 405, { Allow: "GET, HEAD" });
  }
  let datos;
  try {
    const r = await fetch(ORIGEN, { headers: { Accept: "application/json" }, cf: { cacheTtl: 30, cacheEverything: true } });
    if (!r.ok) throw new Error("HTTP " + r.status);
    datos = await r.json();
  } catch (e) {
    return responder({ error: "Las noticias no estan disponibles en este momento", detalle: String(e.message || e) }, 502,
      { "Cache-Control": "no-store" });
  }
  if (!datos || !Array.isArray(datos.noticias)) {
    return responder({ error: "Formato de datos inesperado" }, 502, { "Cache-Control": "no-store" });
  }

  const p = new URL(request.url).searchParams;
  const categoria = sinTildes(p.get("categoria")).trim().replace(/\s+/g, "-");
  const medio = sinTildes(p.get("medio")).trim();
  const q = sinTildes(p.get("q")).trim();
  const pedido = parseInt(p.get("limit") || "", 10);
  const limite = Math.min(Number.isFinite(pedido) && pedido > 0 ? pedido : LIMITE_DEFECTO, LIMITE_MAX);

  let lista = datos.noticias;
  if (categoria) lista = lista.filter((n) => n.categoria === categoria || (n.categorias || []).includes(categoria));
  if (medio) lista = lista.filter((n) => sinTildes(n.medio) === medio);
  if (q) lista = lista.filter((n) => sinTildes(`${n.titulo} ${n.bajada} ${n.medio}`).includes(q));
  const disponibles = lista.length;
  lista = lista.slice(0, limite);

  return responder({
    ultima_actualizacion: datos.ultima_actualizacion,
    total_noticias: lista.length,
    total_disponibles: disponibles,
    nota: datos.nota,
    noticias: lista,
  });
}
