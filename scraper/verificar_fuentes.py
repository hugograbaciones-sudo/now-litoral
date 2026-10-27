verificar_fuentes.py
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FUENTES_FILE = BASE_DIR / "fuentes.json"
INFORME_MD = Path("informe_fuentes.md")
INFORME_JSON = Path("informe_fuentes.json")


def verificar_fuente(fuente):
    nombre = fuente.get("nombre", "Fuente sin nombre")
    url = fuente.get("url", "")

    resultado = {
        "nombre": nombre,
        "url": url,
        "estado": "ERROR",
        "detalle": ""
    }

    if not url:
        resultado["detalle"] = "No tiene URL configurada"
        return resultado

    solicitud = urllib.request.Request(
        url,
        headers={"User-Agent": "NOW-LITORAL/1.0 (verificador de fuentes)"}
    )

    try:
        with urllib.request.urlopen(solicitud, timeout=20) as respuesta:
            codigo = respuesta.getcode()
            resultado["estado"] = "OK" if 200 <= codigo < 400 else "ERROR"
            resultado["detalle"] = f"HTTP {codigo}"

    except urllib.error.HTTPError as error:
        resultado["detalle"] = f"HTTP {error.code}"

    except Exception as error:
        resultado["detalle"] = f"{type(error).__name__}: {error}"

    return resultado


def main():
    if not FUENTES_FILE.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo de fuentes: {FUENTES_FILE}"
        )

    with FUENTES_FILE.open("r", encoding="utf-8") as archivo:
        datos = json.load(archivo)

    fuentes = datos if isinstance(datos, list) else datos.get("fuentes", [])

    if not fuentes:
        raise ValueError(
            "fuentes.json no contiene fuentes. Revisar su estructura."
        )

    resultados = [verificar_fuente(fuente) for fuente in fuentes]
    fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lineas = [
        "# Informe de verificación de fuentes — NOW LITORAL",
        "",
        f"Fecha de verificación: {fecha}",
        "",
        "| Fuente | Estado | Detalle | URL |",
        "|---|---|---|---|"
    ]

    for resultado in resultados:
        lineas.append(
            f"| {resultado['nombre']} | {resultado['estado']} "
            f"| {resultado['detalle']} | {resultado['url']} |"
        )

    INFORME_MD.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    INFORME_JSON.write_text(
        json.dumps(
            {"fecha": fecha, "resultados": resultados},
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    correctas = sum(r["estado"] == "OK" for r in resultados)

    print(f"Verificación terminada: {correctas}/{len(resultados)} fuentes respondieron correctamente.")
    print("Informes generados: informe_fuentes.md e informe_fuentes.json")


if __name__ == "__main__":
    main()
