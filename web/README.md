# NOW LITORAL

Portada de noticias para Gualeguaychú y Entre Ríos, con feeds verificados, espacios publicitarios, radio online preparada y carga asistida de noticias propias.

## Preparar el logo

La portada busca el archivo `web/assets/logo.png`. Copiá allí el logo original:

`I:\1 NOW LITORAL\Logotip 3D de notícies global Litoral.png` → `web\assets\logo.png`

Incluye un logo vectorial de respaldo en `web/assets/logo.svg`.

## Estructura

- `web/`: portada estática lista para Cloudflare Pages.
- `web/data/noticias.json`: noticias recopiladas.
- `web/data/manuales.json`: publicaciones propias compartidas.
- `scraper/`: fuentes RSS y recolector Python.
- `.github/workflows/actualizar-noticias.yml`: actualización manual y cada 30 minutos.

## Probar localmente

Desde la raíz del proyecto:

1. Instalar dependencias: `py -m pip install -r scraper/requirements.txt`
2. Obtener noticias: `py scraper/actualizar_noticias.py`
3. Servir la web: `py -m http.server 8000 --directory web`
4. Abrir `http://127.0.0.1:8000`

Serví el sitio por HTTP local; no abras `index.html` directamente porque el navegador restringe la lectura de JSON en páginas `file://`.

## Publicar

Subí los archivos al repositorio independiente de NOW LITORAL y conservá la estructura. En Cloudflare Pages conectá ese repositorio, dejá vacía la orden de build y elegí `web` como directorio de salida. GitHub Actions actualiza `web/data/noticias.json` y guarda el cambio en el repositorio.

No se usa base de datos ni API comercial. La portada muestra título, resumen breve, medio y enlace original. No reproduce artículos completos ni muestra imágenes de terceros.

## Cargar una noticia propia

El formulario guarda publicaciones en el navegador actual. Para hacerlas visibles en el sitio compartido:

1. Usá “Exportar publicaciones”.
2. Incorporá el contenido exportado dentro de `web/data/manuales.json`, con esta estructura: `{"noticias":[...]}`.
3. Guardá y publicá el cambio en el repositorio.

No se expone una contraseña o token de escritura en el navegador. La edición pública desde un panel multiusuario requiere autenticación y almacenamiento persistente, que queda para una etapa posterior.

## Radio

El reproductor acepta una URL HTTP/HTTPS de streaming. Para dejarla configurada para todos, editá `RADIO_STREAM_URL` al inicio de `web/app.js` y publicá el cambio. El cuadro de configuración del sitio guarda el enlace solo en ese navegador.

## Fuentes

La configuración activa usa 16 feeds que el informe de la ejecución #3 pudo procesar. Infobae corresponde al feed de Estados Unidos; el feed identificado como “El Argentino de Gualeguaychú” devolvió el título “El Argentino Diario”, así que la configuración usa ese nombre para mantener la atribución correcta. Antes de una explotación comercial, revisá los términos de cada medio.