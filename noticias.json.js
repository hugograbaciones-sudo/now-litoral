// NOW LITORAL - /data/noticias.json (lo que lee el portal)
// Entrega el noticias.json que publica el motor, leido desde la rama "datos" del repositorio de GitHub.
// Si GitHub no responde, entrega la copia que viaja con el sitio (web/data/noticias.json), asi el portal nunca queda vacio.

const RAW = "https://raw.githubusercontent.com/hugograbaciones-sudo/now-litoral/datos/";
// El numero cambia cada minuto: evita que el cache de raw.githubusercontent.com (5 min) entregue datos viejos.
const origen = (archivo) => `${RAW}${archivo}?v=${Math.floor(Date.now() / 60000)}`;

const CABECERAS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "public, max-age=30, s-maxage=30",
  "Access-Control-Allow-Origin": "*",
  "X-Content-Type-Options": "nosniff",
  "X-Origen-Datos": "github-datos",
};

export async function onRequest(context) {
  const { request } = context;
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response(JSON.stringify({ error: "Metodo no permitido" }), { status: 405, headers: { ...CABECERAS, Allow: "GET, HEAD", "Cache-Control": "no-store" } });
  }
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const clave = new Request(request.url, { method: "GET" });
  if (cache) {
    const guardada = await cache.match(clave);
    if (guardada) return guardada;
  }
  try {
    const r = await fetch(origen("noticias.json"), { headers: { Accept: "application/json" }, cf: { cacheTtl: 30, cacheEverything: true } });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const respuesta = new Response(r.body, { status: 200, headers: CABECERAS });
    if (cache && context.waitUntil) context.waitUntil(cache.put(clave, respuesta.clone()));
    return respuesta;
  } catch (e) {
    // Respaldo: el archivo estatico del sitio (puede estar desactualizado; el portal lo avisa en pantalla).
    const estatico = await context.next();
    const copia = new Response(estatico.body, estatico);
    copia.headers.set("X-Origen-Datos", "respaldo-estatico");
    copia.headers.set("Cache-Control", "no-store");
    return copia;
  }
}
