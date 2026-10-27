#!/usr/bin/env python3
"""
NOW LITORAL - Verificador de fuentes RSS.

Para cada medio de fuentes.json:
  1. prueba las URLs "candidatos";
  2. busca el feed anunciado en la portada (<link rel="alternate">);
  3. prueba rutas comunes (/feed, /rss, ...).
Mide: respuesta HTTP, cantidad de notas, antiguedad de la ultima, notas en 24 h,
presencia de imagen y resumen, y si robots.txt permite leer esa ruta.
Genera informe_fuentes.json e informe_fuentes.md. No inventa nada: lo que
no se pueda comprobar queda marcado como tal.

Variable opcional: SOLO=bbc_mundo,dw_es  (prueba solo esos ids).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import feedparser
import requests

UA = "NowLitoralBot/0.1 (verificador de fuentes; agregador con atribucion)"
TIMEOUT = 20
REINTENTOS = 2
RUTAS_COMUNES = ["/feed", "/feed/", "/rss", "/rss/", "/rss.xml", "/feed.xml", "/index.xml"]
AR = timezone(timedelta(hours=-3))  # Argentina, UTC-3
AQUI = os.path.dirname(os.path.abspath(__file__))

sesion = requests.Session()
sesion.headers.update({"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5"})


def pedir(url):
    """Devuelve (respuesta|None, codigo|None, error|None, milisegundos)."""
    ultimo_error, codigo, ms = None, None, 0
    for intento in range(REINTENTOS + 1):
        t0 = time.time()
        try:
            r = sesion.get(url, timeout=TIMEOUT, allow_redirects=True)
            ms = int((time.time() - t0) * 1000)
            codigo = r.status_code
            if r.status_code == 200:
                return r, codigo, None, ms
            ultimo_error = f"HTTP {r.status_code}"
            if r.status_code in (401, 403, 404, 410):
                break  # reintentar no sirve
        except requests.RequestException as e:
            ms = int((time.time() - t0) * 1000)
            ultimo_error = type(e).__name__
        time.sleep(2 * (intento + 1))
    return None, codigo, ultimo_error, ms


def fecha_de(entrada):
    for campo in ("published_parsed", "updated_parsed"):
        t = entrada.get(campo)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def tiene_imagen(e):
    if e.get("media_content") or e.get("media_thumbnail"):
        return True
    for enc in e.get("enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image"):
            return True
    for l in e.get("links", []) or []:
        if str(l.get("type", "")).startswith("image"):
            return True
    return bool(re.search(r"<img\s", (e.get("summary", "") or "") + str(e.get("content", ""))))


def analizar_feed(contenido, ahora=None):
    """Analiza el contenido de un feed. Devuelve dict de metricas o None si no es un feed."""
    ahora = ahora or datetime.now(timezone.utc)
    feed = feedparser.parse(contenido)
    notas = feed.entries
    if not notas:
        return None
    fechas = [f for f in (fecha_de(e) for e in notas) if f]
    ultima = max(fechas) if fechas else None
    n = len(notas)
    return {
        "titulo_feed": feed.feed.get("title", ""),
        "notas": n,
        "sin_fecha": n - len(fechas),
        "ultima_nota_utc": ultima.isoformat() if ultima else None,
        "ultima_nota_ar": ultima.astimezone(AR).strftime("%Y-%m-%d %H:%M") if ultima else None,
        "antiguedad_horas": round((ahora - ultima).total_seconds() / 3600, 1) if ultima else None,
        "notas_ultimas_24h": sum(1 for f in fechas if (ahora - f) <= timedelta(hours=24)),
        "con_imagen_pct": round(100 * sum(1 for e in notas if tiene_imagen(e)) / n),
        "con_resumen_pct": round(100 * sum(1 for e in notas if (e.get("summary") or "").strip()) / n),
        "xml_con_errores": bool(feed.get("bozo")),
    }


def descubrir_en_portada(home):
    """Devuelve (feeds_anunciados, codigo_http_portada, error)."""
    r, codigo, error, _ = pedir(home)
    if not r:
        return [], codigo, error
    hallados = []
    for tag in re.findall(r"<link\b[^>]*>", r.text[:300000], flags=re.I):
        if re.search(r"alternate", tag, re.I) and re.search(r"application/(rss|atom)\+xml", tag, re.I):
            m = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
            if m:
                hallados.append(urljoin(r.url, m.group(1)))
    return hallados, 200, None


def robots_permite(url):
    p = urlparse(url)
    r, _, _, _ = pedir(f"{p.scheme}://{p.netloc}/robots.txt")
    if not r:
        return None  # no se pudo comprobar
    rp = robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(UA, url)


def verificar(fuente):
    home = fuente["home"].rstrip("/")
    origen = f"{urlparse(home).scheme}://{urlparse(home).netloc}"
    candidatos = list(fuente.get("candidatos", []))
    intentos, vistos, codigos = [], set(), []

    def probar(url, origen_url):
        if url in vistos:
            return None
        vistos.add(url)
        r, codigo, error, ms = pedir(url)
        codigos.append(codigo)
        if not r:
            intentos.append({"url": url, "origen": origen_url, "resultado": error or "sin respuesta", "ms": ms})
            return None
        metricas = analizar_feed(r.content)
        if not metricas:
            intentos.append({"url": url, "origen": origen_url, "resultado": "responde pero no es un feed valido", "ms": ms})
            return None
        intentos.append({"url": url, "origen": origen_url, "resultado": "OK", "ms": ms})
        metricas.update({"url_feed": url, "content_type": r.headers.get("Content-Type", ""), "ms": ms})
        return metricas

    ganador = None
    cod_home = None
    for u in candidatos:
        ganador = probar(u, "candidato")
        if ganador:
            break
    if not ganador:
        anunciados, cod_home, err_home = descubrir_en_portada(home)
        if cod_home != 200:
            intentos.append({"url": home, "origen": "portada", "resultado": err_home or "sin respuesta", "ms": 0})
        for u in anunciados:
            ganador = probar(u, "portada")
            if ganador:
                break
    if not ganador:
        for ruta in RUTAS_COMUNES:
            ganador = probar(origen + ruta, "ruta comun")
            if ganador:
                break

    res = {"id": fuente["id"], "nombre": fuente["nombre"], "categoria": fuente["categoria"], "home": fuente["home"], "intentos": intentos}
    if ganador:
        res.update(ganador)
        res["robots_permite"] = robots_permite(ganador["url_feed"])
        old = ganador["antiguedad_horas"]
        res["estado"] = "OK" if old is not None and old <= 48 else "OK_DESACTUALIZADO"
    else:
        validos = [c for c in codigos if c]
        portada_bloqueada = cod_home in (401, 403, 429)
        todo_bloqueado = bool(validos) and all(c in (401, 403, 429) for c in validos)
        res["estado"] = "BLOQUEADO" if (portada_bloqueada or todo_bloqueado) else "SIN_FEED"
    return res


def informe_md(resultados, generado):
    iconos = {"OK": "OK", "OK_DESACTUALIZADO": "VIEJO", "BLOQUEADO": "BLOQUEADO", "SIN_FEED": "SIN FEED"}
    out = [f"# Informe de fuentes - NOW LITORAL", "", f"Generado: {generado} (hora Argentina)", ""]
    cuenta = {}
    for r in resultados:
        cuenta[r["estado"]] = cuenta.get(r["estado"], 0) + 1
    out.append("Resumen: " + ", ".join(f"{iconos.get(k, k)}: {v}" for k, v in sorted(cuenta.items())))
    out += ["", "| Medio | Estado | Notas | Ultima nota (AR) | Notas 24 h | Imagen % | Resumen % | robots.txt | Feed |", "|---|---|---|---|---|---|---|---|---|"]
    for r in resultados:
        rob = {True: "permite", False: "NO permite", None: "no comprobado"}[r.get("robots_permite")] if r["estado"].startswith("OK") else "-"
        out.append("| {n} | {e} | {c} | {u} | {h} | {i} | {s} | {rb} | {f} |".format(
            n=r["nombre"], e=iconos.get(r["estado"], r["estado"]), c=r.get("notas", "-"),
            u=r.get("ultima_nota_ar", "-"), h=r.get("notas_ultimas_24h", "-"), i=r.get("con_imagen_pct", "-"),
            s=r.get("con_resumen_pct", "-"), rb=rob, f=r.get("url_feed", "-")))
    fallidas = [r for r in resultados if r["estado"] in ("SIN_FEED", "BLOQUEADO")]
    if fallidas:
        out += ["", "## Fuentes sin feed utilizable (intentos)", ""]
        for r in fallidas:
            out.append(f"**{r['nombre']}** ({r['estado']})")
            for i in r["intentos"]:
                out.append(f"- {i['url']} -> {i['resultado']}")
            out.append("")
    out += ["", "Nota: este informe NO evalua los terminos de uso de cada medio. Antes de integrar una fuente hay que revisarlos a mano."]
    return "\n".join(out)


def main():
    with open(os.path.join(AQUI, "fuentes.json"), encoding="utf-8") as f:
        fuentes = json.load(f)["fuentes"]
    solo = [s.strip() for s in os.environ.get("SOLO", "").split(",") if s.strip()]
    if solo:
        fuentes = [f for f in fuentes if f["id"] in solo]
    resultados = []
    for i, fu in enumerate(fuentes, 1):
        print(f"[{i}/{len(fuentes)}] {fu['nombre']} ...", flush=True)
        try:
            r = verificar(fu)
        except Exception as e:  # una fuente rota no debe frenar a las demas
            r = {"id": fu["id"], "nombre": fu["nombre"], "categoria": fu["categoria"], "home": fu["home"], "intentos": [], "estado": "SIN_FEED", "error_interno": f"{type(e).__name__}: {e}"}
        print(f"    -> {r['estado']}", flush=True)
        resultados.append(r)
        time.sleep(1)
    generado = datetime.now(AR).strftime("%Y-%m-%d %H:%M")
    with open("informe_fuentes.json", "w", encoding="utf-8") as f:
        json.dump({"generado_ar": generado, "resultados": resultados}, f, ensure_ascii=False, indent=2)
    md = informe_md(resultados, generado)
    with open("informe_fuentes.md", "w", encoding="utf-8") as f:
        f.write(md)
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write(md)
    print("\nListo. Archivos: informe_fuentes.json e informe_fuentes.md")


if __name__ == "__main__":
    sys.exit(main())
