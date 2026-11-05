const REPO = "hugograbaciones-sudo/now-litoral";
const WORKFLOW = "actualizar-noticias.yml";
const RAMA = "main";
const INTENTOS = 3;

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

async function disparar(env, cron) {
  if (!env.GITHUB_TOKEN) {
    throw new Error("Falta el secreto GITHUB_TOKEN en Cloudflare.");
  }

  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;

  let ultimoError = "";

  for (let intento = 1; intento <= INTENTOS; intento++) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "now-litoral-disparador",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: RAMA }),
      });

      if (r.status === 204) {
        console.log(`OK: actualización solicitada. Cron: ${cron}`);
        return;
      }

      const detalle = (await r.text()).slice(0, 300);
      ultimoError = `GitHub respondió ${r.status}: ${detalle}`;

      if (r.status < 500 && r.status !== 429) break;
    } catch (e) {
      ultimoError = `No se pudo conectar con GitHub (${e.message || e})`;
    }

    if (intento < INTENTOS) await esperar(2000 * intento);
  }

  throw new Error(ultimoError);
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(disparar(env, controller.cron));
  },

  async fetch() {
    return new Response(
      "Disparador de NOW LITORAL: solo actúa en los horarios programados.",
      { status: 200, headers: { "Content-Type": "text/plain; charset=utf-8" } }
    );
  },
};