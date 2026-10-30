#!/usr/bin/env python3
"""NOW LITORAL - motor de noticias.

Cada ejecucion:
  1. Descarga los RSS de scraper/fuentes_motor.json (en paralelo, con reintentos).
  2. Convierte cada nota: titulo, medio, fecha UTC, resumen limpio, imagen (si el feed la trae),
     enlace sin parametros de seguimiento y secciones.
  3. Descarga el noticias.json ya publicado y lo FUSIONA (historial de 72 h), sin duplicados.
  4. Si una fuente falla, conserva sus notas anteriores y registra el error.
  5. Escribe salida/noticias.json (+ index.html y un resumen para GitHub Actions).

Si NINGUNA fuente responde, termina con error y no escribe nada (asi no se publica un JSON vacio).
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import requests

TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")
UA = "NowLitoralBot/1.0 (+https://now-litoral.pages.dev; agregador periodistico)"
HISTORIAL_HORAS = 72
MAX_TOTAL = 600          # tope de notas en el archivo (mantiene el JSON liviano para el celular)
MAX_POR_MEDIO = 60       # evita que un solo medio llene el portal
MAX_RESUMEN = 300
TIMEOUT = 20
PARAMETROS_SEGUIMIENTO = {"at_medium", "at_campaign", "at_custom1", "fbclid", "gclid", "ref", "ocid", "cmpid"}

# Seccion segun el tramo de la URL de la nota.
RUTAS = {
    "politica": "Política",
    "economia": "Economía", "finanzas": "Economía", "negocios": "Economía",
    "sociedad": "Sociedad",
    "seguridad": "Policiales", "policiales": "Policiales", "judiciales": "Policiales",
    "deportes": "Deportes", "futbol": "Deportes", "polideportivo": "Deportes",
    "espectaculos": "Espectáculos", "show": "Espectáculos", "entretenimiento": "Espectáculos",
    "cultura": "Espectáculos", "arte-cultura": "Espectáculos", "cine": "Espectáculos",
    "el-mundo": "Internacionales", "mundo": "Internacionales", "internacional": "Internacionales",
    "internacionales": "Internacionales", "america": "Internacionales", "europa": "Internacionales",
    "campo": "Agro y producción", "rural": "Agro y producción", "agro": "Agro y producción",
    "tecno": "Tecnología", "tecnologia": "Tecnología",
}
RUTAS_SOLO_HOST = {"estados-unidos": ("infobae", "clarin")}   # en TN, por ejemplo, esa ruta no es una seccion

SITIO = "https://now-litoral.pages.dev"
# Mapa nombre-de-medio -> logotipo guardado en el propio proyecto (lo genera scraper/logos_medios.py)
LOGOS_URL = os.environ.get("LOGOS_URL", f"{SITIO}/assets/medios/medios.json")
PRIORIDAD_SLUGS = ["gualeguaychu", "entre-rios", "deportes", "tecnologia", "internacionales", "policiales",
                   "politica", "economia", "espectaculos", "agro", "sociedad", "argentina"]
ALIAS_SLUG = {"tecnologia-e-ia": "tecnologia", "agro-y-produccion": "agro"}
SUBCATEGORIAS_DEPORTE = {"futbol": "fútbol", "tenis": "tenis", "basquet": "básquet", "rugby": "rugby",
                         "automovilismo": "automovilismo", "formula-1": "Fórmula 1", "boxeo": "boxeo",
                         "hockey": "hockey", "voley": "vóley", "golf": "golf", "ciclismo": "ciclismo"}


def ahora_utc():
    return datetime.now(timezone.utc)


def iso_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn")


# ---------- Limpieza ----------
def limpiar_url(u):
    """Quita parametros de seguimiento y el fragmento; sirve tambien como clave contra duplicados."""
    try:
        p = urlsplit(str(u).strip())
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    consulta = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                if not k.lower().startswith("utm_") and k.lower() not in PARAMETROS_SEGUIMIENTO]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(consulta), ""))


def limpiar_texto(v):
    t = re.sub(r"<[^>]+>", " ", str(v or ""))
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def resumir(v):
    t = limpiar_texto(v)
    t = re.sub(r"\s*Leer más\s*$", "", t, flags=re.I).strip()
    if len(t) > MAX_RESUMEN:
        t = t[:MAX_RESUMEN].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"
    return t


def imagen_de(e):
    candidatas = []
    for k in ("media_content", "media_thumbnail"):
        for m in e.get(k, []) or []:
            candidatas.append((m.get("url"), m.get("type", "image")))
    for enc in e.get("enclosures", []) or []:
        candidatas.append((enc.get("href") or enc.get("url"), enc.get("type", "")))
    for lk in e.get("links", []) or []:
        if lk.get("rel") == "enclosure":
            candidatas.append((lk.get("href"), lk.get("type", "")))
    for url, tipo in candidatas:
        if url and str(tipo).startswith("image") and str(url).startswith("https://"):
            return url
    cuerpo = str(e.get("summary", "")) + " ".join(c.get("value", "") for c in e.get("content", []) or [])
    m = re.search(r'<img[^>]+src=["\'](https://[^"\']+)["\']', cuerpo, flags=re.I)
    return m.group(1) if m else None


# ---------- Secciones ----------
def secciones_por_ruta(url):
    p = urlsplit(url)
    host = p.netloc.lower()
    encontradas = []
    for seg in p.path.lower().split("/"):
        if not seg or seg.isdigit() or re.fullmatch(r"\d{4}-\d{2}-\d{2}", seg):
            continue
        cat = RUTAS.get(seg)
        if seg in RUTAS_SOLO_HOST and not any(h in host for h in RUTAS_SOLO_HOST[seg]):
            cat = None
        if cat and cat not in encontradas:
            encontradas.append(cat)
    return encontradas


def clasificar(fuente, url, titulo, resumen):
    cats = list(fuente.get("categorias_fijas", []))
    if fuente.get("clasificar"):
        cats += [c for c in secciones_por_ruta(url) if c not in cats]
        if fuente.get("argentina") and cats != ["Internacionales"]:
            cats.append("Argentina")
    texto = sin_tildes(f"{titulo} {resumen}")
    if "gualeguaychu" in texto:
        cats += [c for c in ("Gualeguaychú", "Entre Ríos") if c not in cats]
    elif "entre rios" in texto or "entrerrian" in texto:
        cats += [c for c in ("Entre Ríos",) if c not in cats]
    return cats or ["Argentina"]


# ---------- Descarga ----------
def descargar(url, reintentos=2):
    error = None
    for intento in range(reintentos + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT, headers={
                "User-Agent": UA,
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"})
            if r.status_code == 200:
                return r.content, None
            error = f"HTTP {r.status_code}"
            if r.status_code in (401, 403, 404, 410):   # no tiene sentido reintentar
                break
        except requests.RequestException as ex:
            error = type(ex).__name__
        time.sleep(1.5 * (intento + 1))
    return None, error


def convertir(e, fuente, ahora):
    titulo = limpiar_texto(e.get("title"))
    enlace = limpiar_url(e.get("link"))
    if not titulo or not enlace:
        return None
    t = e.get("published_parsed") or e.get("updated_parsed")
    fecha_real = bool(t)
    fecha = datetime(*t[:6], tzinfo=timezone.utc) if t else ahora
    if fecha > ahora + timedelta(minutes=10):
        fecha = ahora
    resumen = resumir(e.get("summary") or e.get("description"))
    nota = {
        "id": hashlib.sha1(enlace.encode("utf-8")).hexdigest(),
        "titulo": titulo,
        "medio": fuente["nombre"],
        "publicado_en": iso_utc(fecha),
        "categorias": clasificar(fuente, enlace, titulo, resumen),
        "resumen": resumen,
        "enlace": enlace,
    }
    img = imagen_de(e)
    if img:
        nota["imagen"] = img
    nota["_fecha_real"] = fecha_real
    return nota


def procesar_fuente(fuente, ahora):
    res = {"id": fuente["id"], "nombre": fuente["nombre"], "estado": "ERROR", "url_feed": None,
           "noticias": 0, "error": None}
    notas = []
    for url in fuente["feeds"]:
        data, error = descargar(url)
        if data is None:
            res["error"] = f"{url} -> {error}"
            continue
        d = feedparser.parse(data)
        convertidas = [n for n in (convertir(e, fuente, ahora) for e in d.entries) if n]
        if not convertidas:
            res["error"] = f"{url} -> sin notas legibles"
            continue
        notas = convertidas
        res.update(estado="OK", url_feed=url, noticias=len(convertidas), error=None)
        break
    return res, notas


# ---------- Historial ----------
def cargar_previas(origenes):
    for o in origenes:
        o = o.strip()
        if not o:
            continue
        try:
            if os.path.exists(o):
                d = json.loads(Path(o).read_text(encoding="utf-8"))
            else:
                r = requests.get(o, timeout=TIMEOUT, headers={"User-Agent": UA})
                if r.status_code != 200:
                    continue
                d = r.json()
            if isinstance(d.get("noticias"), list):
                return d, o
        except (OSError, ValueError, requests.RequestException):
            continue
    return None, None


def fusionar(previas, nuevas, ahora):
    por_enlace = {}
    for n in previas:
        enlace = limpiar_url(n.get("enlace"))
        if not enlace or not n.get("titulo") or not n.get("medio") or not n.get("publicado_en"):
            continue
        n = dict(n, enlace=enlace, id=hashlib.sha1(enlace.encode("utf-8")).hexdigest())
        por_enlace[enlace] = n
    for n in nuevas:
        previa = por_enlace.get(n["enlace"])
        fecha_real = n.pop("_fecha_real", True)
        if previa:
            if not fecha_real:
                n["publicado_en"] = previa["publicado_en"]   # sin fecha propia: conservar la primera vez que se vio
            if "imagen" not in n and previa.get("imagen"):
                n["imagen"] = previa["imagen"]
        por_enlace[n["enlace"]] = n
    limite = iso_utc(ahora - timedelta(hours=HISTORIAL_HORAS))
    vigentes = [n for n in por_enlace.values() if n["publicado_en"] >= limite]
    vigentes.sort(key=lambda n: n["publicado_en"], reverse=True)
    por_medio, resultado = {}, []
    for n in vigentes:
        por_medio[n["medio"]] = por_medio.get(n["medio"], 0) + 1
        if por_medio[n["medio"]] <= MAX_POR_MEDIO:
            resultado.append(n)
    return resultado[:MAX_TOTAL]


# ---------- news.json: salida publica simple para lectores automaticos (por ejemplo ChatGPT) ----------
def slug(etiqueta):
    base = re.sub(r"\s+", "-", sin_tildes(etiqueta).strip())
    return ALIAS_SLUG.get(base, base)


def cargar_logos(origen=LOGOS_URL):
    """nombre de medio -> URL absoluta del logotipo guardado en el sitio. Si no hay mapa, devuelve {}."""
    try:
        if os.path.exists(origen):
            d = json.loads(Path(origen).read_text(encoding="utf-8"))
        else:
            r = requests.get(origen, timeout=TIMEOUT, headers={"User-Agent": UA})
            if r.status_code != 200:
                return {}
            d = r.json()
    except (OSError, ValueError, requests.RequestException):
        return {}
    logos = {}
    for nombre, info in (d.get("medios") or {}).items():
        archivo = (info or {}).get("archivo")
        if isinstance(archivo, str) and re.fullmatch(r"[\w.-]+\.(webp|png|jpe?g|svg)", archivo, flags=re.I):
            logos[nombre] = f"{SITIO}/assets/medios/{archivo}"
    return logos


def subcategoria_de(enlace, categoria):
    if categoria != "deportes":
        return None
    for seg in urlsplit(enlace).path.lower().split("/"):
        if seg in SUBCATEGORIAS_DEPORTE:
            return SUBCATEGORIAS_DEPORTE[seg]
    return None


def armar_news_json(salida, logos):
    items = []
    for n in salida["noticias"]:
        slugs = []
        for c in n.get("categorias", []):
            sg = slug(c)
            if sg in PRIORIDAD_SLUGS and sg not in slugs:
                slugs.append(sg)
        if "gualeguaychu" in slugs and "entre-rios" not in slugs:
            slugs.append("entre-rios")
        categoria = next((c for c in PRIORIDAD_SLUGS if c in slugs), "argentina")
        items.append({
            "id": n["id"],
            "titulo": n["titulo"],
            "bajada": n.get("resumen", ""),
            "desarrollo": None,   # agregador: el texto completo esta en el medio original (url_fuente)
            "categoria": categoria,
            "categorias": slugs or [categoria],
            "subcategoria": subcategoria_de(n["enlace"], categoria),
            "fecha_publicacion": n["publicado_en"],
            "medio": n["medio"],
            "fuente": n["medio"],
            "url_fuente": n["enlace"],
            "logo_medio": logos.get(n["medio"]),
            "imagen": n.get("imagen"),
        })
    return {
        "ultima_actualizacion": salida["generado_en"],
        "total_noticias": len(items),
        "nota": ("NOW LITORAL es un agregador periodistico: cada noticia incluye titulo, bajada (extracto) y enlace "
                 "a la nota completa en el medio original (url_fuente). No reproduce articulos completos."),
        "noticias": items,
    }


def main():
    ap = argparse.ArgumentParser(description="Motor de noticias NOW LITORAL")
    ap.add_argument("--fuentes", default=str(Path(__file__).with_name("fuentes_motor.json")))
    ap.add_argument("--salida", default="salida")
    ap.add_argument("--anterior", default=os.environ.get("URL_ANTERIOR", ""),
                    help="URL(s) o archivo(s) del noticias.json anterior, separados por coma")
    args = ap.parse_args()

    ahora = ahora_utc()
    fuentes = json.loads(Path(args.fuentes).read_text(encoding="utf-8"))["fuentes"]
    print(f"Consultando {len(fuentes)} fuentes...", flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(lambda f: procesar_fuente(f, ahora), fuentes))

    estados = [r for r, _ in resultados]
    nuevas = [n for _, notas in resultados for n in notas]
    ok = [r for r in estados if r["estado"] == "OK"]

    previa, origen = cargar_previas(args.anterior.split(","))
    print(f"Historial previo: {len(previa['noticias']) if previa else 0} notas" + (f" (desde {origen})" if origen else " (primera ejecucion)"), flush=True)

    if not ok:
        print("ERROR: ninguna fuente respondio; no se publica nada para no pisar el contenido anterior.", file=sys.stderr)
        for r in estados:
            print(f" - {r['nombre']}: {r['error']}", file=sys.stderr)
        return 1

    ultimo_ok_prev = {f.get("id"): f.get("ultimo_ok") for f in (previa or {}).get("fuentes", [])}
    for r in estados:
        r["ultimo_ok"] = iso_utc(ahora) if r["estado"] == "OK" else ultimo_ok_prev.get(r["id"])
        if r["error"] is None:
            del r["error"]

    noticias = fusionar((previa or {}).get("noticias", []), nuevas, ahora)
    salida = {
        "generado_en": ahora.astimezone(TZ_AR).isoformat(timespec="seconds"),
        "historial_horas": HISTORIAL_HORAS,
        "fuentes": estados,
        "noticias": noticias,
    }
    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)
    (out / "noticias.json").write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "news.json").write_text(
        json.dumps(armar_news_json(salida, cargar_logos()), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>NOW LITORAL - datos</title>"
        "<p>Datos de NOW LITORAL. Ver <a href='noticias.json'>noticias.json</a> y <a href='news.json'>news.json</a>.</p>", encoding="utf-8")

    resumen = [f"## Motor de noticias - {salida['generado_en']}", "",
               f"Fuentes OK: {len(ok)}/{len(estados)} · notas nuevas leidas: {len(nuevas)} · notas publicadas: {len(noticias)}", "",
               "| Fuente | Estado | Notas | Detalle |", "|---|---|---|---|"]
    for r in estados:
        resumen.append(f"| {r['nombre']} | {r['estado']} | {r['noticias']} | {r.get('error', '')} |")
    texto = "\n".join(resumen)
    print(texto, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(texto + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
