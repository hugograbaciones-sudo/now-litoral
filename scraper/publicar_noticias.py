#!/usr/bin/env python3
"""Actualiza el JSON público de NOW LITORAL desde feeds RSS/Atom."""
import hashlib
import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib import robotparser

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "scraper" / "fuentes.json"
SALIDA = ROOT / "web" / "data" / "noticias.json"
AR = timezone(timedelta(hours=-3))
UA = "NOWLITORAL/1.0 (+https://now-litoral.pages.dev; agregador RSS con atribucion)"
TIMEOUT = 18
VENTANA_HORAS = 72
MAX_POR_FUENTE = 60
MAX_NOTICIAS = 600

sesion = requests.Session()
sesion.headers.update({"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8"})
robots_cache = {}

CATEGORIAS = {
    "gualeguaychu": ["Locales", "Gualeguaychú"],
    "entre_rios": ["Entre Ríos"],
    "argentina": ["Argentina"],
    "economia": ["Economía"],
    "deportes": ["Deportes"],
    "internacionales": ["Internacionales"],
    "tecnologia": ["Tecnología"],
}


def permiso_robots(url):
    """Devuelve True/False si robots.txt se pudo leer; None si no se pudo comprobar."""
    p = urlparse(url)
    origen = f"{p.scheme}://{p.netloc}"
    if origen not in robots_cache:
        try:
            r = sesion.get(origen + "/robots.txt", timeout=10)
            if r.status_code != 200:
                robots_cache[origen] = None
            else:
                rp = robotparser.RobotFileParser()
                rp.set_url(origen + "/robots.txt")
                rp.parse(r.text.splitlines())
                robots_cache[origen] = rp
        except requests.RequestException:
            robots_cache[origen] = None
    rp = robots_cache[origen]
    return rp.can_fetch(UA, url) if rp else None


def descubrir_feeds(home):
    """Lee solo los RSS/Atom declarados por la portada del medio."""
    try:
        r = sesion.get(home, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        hallados = []
        for tag in re.findall(r"<link\b[^>]*>", r.text[:300000], flags=re.I):
            rel = re.search(r"\brel=[\"']([^\"']+)[\"']", tag, flags=re.I)
            tipo = re.search(r"\btype=[\"']([^\"']+)[\"']", tag, flags=re.I)
            href = re.search(r"\bhref=[\"']([^\"']+)[\"']", tag, flags=re.I)
            if rel and tipo and href and "alternate" in rel.group(1).lower() and re.search(r"application/(rss|atom)\+xml", tipo.group(1), re.I):
                hallados.append(urljoin(r.url, html.unescape(href.group(1))))
        return hallados
    except requests.RequestException:
        return []


def fecha_iso(item):
    for campo in ("published_parsed", "updated_parsed"):
        fecha = item.get(campo)
        if fecha:
            return datetime(*fecha[:6], tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return None


def texto_plano(valor):
    valor = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", valor or "")
    valor = re.sub(r"(?s)<[^>]+>", " ", valor)
    return re.sub(r"\s+", " ", html.unescape(valor)).strip()


def categoria(fuente):
    return CATEGORIAS.get(fuente.get("categoria", ""), ["Noticias"])


def leer_fuente(fuente, ahora):
    urls = list(fuente.get("candidatos", []))
    urls += descubrir_feeds(fuente["home"])
    urls = list(dict.fromkeys(urls))
    ultimo_codigo = None
    for url in urls:
        permiso = permiso_robots(url)
        if permiso is False:
            continue
        try:
            r = sesion.get(url, timeout=TIMEOUT)
            ultimo_codigo = r.status_code
            if r.status_code != 200:
                continue
            feed = feedparser.parse(r.content)
            if not feed.entries:
                continue
            items = []
            for entrada in feed.entries:
                link = entrada.get("link", "")
                if not link or urlparse(link).scheme not in ("http", "https"):
                    continue
                publicada = fecha_iso(entrada)
                if publicada:
                    dt = datetime.fromisoformat(publicada.replace("Z", "+00:00"))
                    if ahora - dt > timedelta(hours=VENTANA_HORAS):
                        continue
                resumen = texto_plano(entrada.get("summary", ""))
                if not resumen and entrada.get("content"):
                    resumen = texto_plano(entrada.content[0].get("value", ""))
                identidad = str(entrada.get("id") or link).strip()
                items.append({
                    "id": hashlib.sha1(identidad.encode("utf-8")).hexdigest(),
                    "titulo": texto_plano(entrada.get("title", ""))[:220] or "Noticia",
                    "medio": fuente["nombre"],
                    "publicado_en": publicada,
                    "categorias": categoria(fuente),
                    "resumen": resumen[:320],
                    "enlace": link,
                })
                if len(items) >= MAX_POR_FUENTE:
                    break
            if items:
                return {"id": fuente["id"], "nombre": fuente["nombre"], "estado": "OK", "url_feed": r.url, "noticias": len(items)}, items
        except (requests.RequestException, ValueError, TypeError) as exc:
            print(f"  {fuente['nombre']}: {type(exc).__name__}")
    estado = "BLOQUEADO" if ultimo_codigo in (401, 403, 429) else "SIN_FEED"
    return {"id": fuente["id"], "nombre": fuente["nombre"], "estado": estado, "noticias": 0}, []


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    ahora = datetime.now(timezone.utc)
    noticias, fuentes = [], []
    vistos = set()
    for fuente in config.get("fuentes", []):
        print(f"Buscando {fuente['nombre']}...", flush=True)
        estado, items = leer_fuente(fuente, ahora)
        fuentes.append(estado)
        for item in items:
            if item["enlace"] not in vistos:
                vistos.add(item["enlace"])
                noticias.append(item)
        print(f"  {estado['estado']}: {len(items)} titulares", flush=True)
        time.sleep(0.25)
    noticias.sort(key=lambda x: x.get("publicado_en") or "", reverse=True)
    noticias = noticias[:MAX_NOTICIAS]
    if not noticias and SALIDA.exists():
        anterior = json.loads(SALIDA.read_text(encoding="utf-8"))
        if anterior.get("noticias"):
            print("Ningún feed respondió; se conserva la última portada válida.")
            return
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    documento = {
        "generado_en": datetime.now(AR).isoformat(timespec="minutes"),
        "historial_horas": VENTANA_HORAS,
        "fuentes": fuentes,
        "noticias": noticias,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    activas = sum(1 for f in fuentes if f["estado"] == "OK")
    print(f"Portada lista: {len(noticias)} noticias de {activas} medios.")


if __name__ == "__main__":
    main()
