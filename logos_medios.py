#!/usr/bin/env python3
"""NOW LITORAL - logotipos de los medios.

Busca la identidad de cada medio y guarda una copia optimizada DENTRO del proyecto
(web/assets/medios/), para que no dependa de servidores ajenos. No inventa nada.

Orden de busqueda para cada medio:
  1. Imagen del canal del propio RSS (la que el medio publica como su logo).
  2. Etiqueta og:logo, apple-touch-icon o icono grande de la portada del medio.
Si no hay una imagen confiable (al menos 64 px), NO se guarda logo y el portal muestra
el nombre del medio con tipografia limpia.

Logo oficial a mano: guardar el archivo en web/assets/medios/ con el nombre <id>.manual.png
(o .webp, .jpg, .svg), por ejemplo infobae.manual.png, y volver a ejecutar este proceso.
Los logos manuales tienen prioridad y nunca se pisan.
"""
import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import feedparser
import requests
from PIL import Image, UnidentifiedImageError

UA = "NowLitoralBot/1.0 (+https://now-litoral.pages.dev; busqueda de logotipos)"
TIMEOUT = 20
MAX_BYTES = 2_000_000
MIN_LADO = 64               # menos que esto se ve borroso en pantalla
MAX_CAJA = (320, 120)       # tamaño maximo guardado (se muestra a ~30 px de alto, esto cubre pantallas de alta densidad)
EXT_MANUAL = (".png", ".webp", ".jpg", ".jpeg", ".svg")


class BuscadorIconos(HTMLParser):
    """Lee <link rel=apple-touch-icon|icon> y <meta property=og:logo> de la portada."""
    def __init__(self):
        super().__init__()
        self.iconos = []   # (prioridad, lado_declarado, url)

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta" and a.get("property", "").lower() == "og:logo" and a.get("content"):
            self.iconos.append((0, 9999, a["content"]))
        if tag == "link" and a.get("href"):
            rel = a.get("rel", "").lower()
            tam = re.match(r"(\d+)x(\d+)", a.get("sizes", ""))
            lado = int(tam.group(1)) if tam else 0
            if "apple-touch-icon" in rel:
                self.iconos.append((1, lado or 180, a["href"]))
            elif "icon" in rel and not a.get("href", "").lower().endswith(".svg") and lado >= MIN_LADO:
                self.iconos.append((2, lado, a["href"]))


def pedir(url):
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA}, stream=True)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        datos = r.raw.read(MAX_BYTES + 1, decode_content=True)
        if len(datos) > MAX_BYTES:
            return None, "archivo demasiado grande"
        return datos, None
    except requests.RequestException as e:
        return None, type(e).__name__


def optimizar(datos):
    """Devuelve (imagen_PIL, error). Recorta margenes transparentes y limita el tamaño."""
    try:
        im = Image.open(io.BytesIO(datos))
        im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return None, "no es una imagen valida"
    im = im.convert("RGBA")
    if min(im.size) < MIN_LADO:
        return None, f"muy chica ({im.size[0]}x{im.size[1]})"
    caja = im.getchannel("A").getbbox()
    if caja and caja != (0, 0, *im.size):
        im = im.crop(caja)
    im.thumbnail(MAX_CAJA, Image.LANCZOS)
    return im, None


def candidatas(fuente):
    """Genera (origen, url) en orden de confianza."""
    d = feedparser.parse(pedir(fuente["feeds"][0])[0] or b"")
    for clave in ("image", "logo", "icon"):
        v = d.feed.get(clave)
        url = (v.get("href") or v.get("url")) if isinstance(v, dict) else v
        if url:
            yield "rss", urljoin(fuente["feeds"][0], str(url))
    web = fuente.get("web")
    if web:
        html_bytes, _ = pedir(web)
        if html_bytes:
            b = BuscadorIconos()
            try:
                b.feed(html_bytes.decode("utf-8", errors="replace"))
            except Exception:
                pass
            for prio, lado, url in sorted(b.iconos, key=lambda x: (x[0], -x[1])):
                yield ("og:logo" if prio == 0 else "icono-portada"), urljoin(web, url)


def logo_manual(carpeta, id_):
    for ext in EXT_MANUAL:
        p = carpeta / f"{id_}.manual{ext}"
        if p.exists():
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description="Logotipos de los medios de NOW LITORAL")
    ap.add_argument("--fuentes", default=str(Path(__file__).with_name("fuentes_motor.json")))
    ap.add_argument("--salida", default="web/assets/medios")
    ap.add_argument("--forzar", action="store_true", help="volver a buscar tambien los medios que ya tienen logo")
    args = ap.parse_args()

    fuentes = json.loads(Path(args.fuentes).read_text(encoding="utf-8"))["fuentes"]
    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    indice_path = carpeta / "medios.json"
    previo = {}
    if indice_path.exists():
        try:
            previo = json.loads(indice_path.read_text(encoding="utf-8")).get("medios", {})
        except ValueError:
            previo = {}

    medios, informe = {}, []
    for f in fuentes:
        id_, nombre = f["id"], f["nombre"]
        manual = logo_manual(carpeta, id_)
        if manual:
            medios[nombre] = {"id": id_, "archivo": manual.name, "origen": "manual"}
            informe.append((nombre, "manual", manual.name, ""))
            continue
        existente = previo.get(nombre)
        if existente and (carpeta / existente.get("archivo", "")).exists() and not args.forzar:
            medios[nombre] = existente
            informe.append((nombre, existente.get("origen", "?"), existente["archivo"], "ya existia"))
            continue
        motivo = "sin imagen candidata"
        for origen, url in candidatas(f):
            datos, error = pedir(url)
            if datos is None:
                motivo = f"{origen}: {error}"
                continue
            im, error = optimizar(datos)
            if im is None:
                motivo = f"{origen}: {error}"
                continue
            archivo = f"{id_}.webp"
            im.save(carpeta / archivo, "WEBP", quality=90, method=6)
            medios[nombre] = {"id": id_, "archivo": archivo, "origen": origen, "fuente_url": url,
                              "ancho": im.size[0], "alto": im.size[1]}
            informe.append((nombre, origen, archivo, f"{im.size[0]}x{im.size[1]}"))
            break
        else:
            informe.append((nombre, "SIN LOGO", "", motivo))

    indice = {"version": 1, "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "medios": medios}
    indice_path.write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")

    lineas = ["## Logotipos de los medios", "", "| Medio | Origen | Archivo | Detalle |", "|---|---|---|---|"]
    lineas += [f"| {n} | {o} | {a} | {d} |" for n, o, a, d in informe]
    sin = [n for n, o, _, _ in informe if o == "SIN LOGO"]
    lineas += ["", f"Con logo: {len(medios)}/{len(fuentes)}." + (f" Sin logo (el portal muestra su nombre): {', '.join(sin)}." if sin else "")]
    texto = "\n".join(lineas)
    print(texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(texto + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
