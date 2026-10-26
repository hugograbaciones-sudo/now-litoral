# NOW LITORAL

Central de noticias digital. Este repositorio es independiente de cualquier otro proyecto.

## Paso 0: verificar las fuentes (lo que contiene esta entrega)

Antes de construir nada, se comprueba qué medios tienen RSS real y funcionando. El workflow puede ejecutarse manualmente y también una vez al día.

### 1. Crear el repositorio en GitHub
1. Entra a https://github.com e inicia sesion (o crea una cuenta gratis).
2. Arriba a la derecha: **+** -> **New repository**.
3. Nombre: `now-litoral`. Marca **Public**. Clic en **Create repository**.

### 2. Subir los archivos
1. En el repositorio nuevo: **Add file** -> **Upload files**.
2. Arrastra desde tu computadora la carpeta `scraper`, la carpeta `.github` y el archivo `README.md`.
   Importante: deben conservar esta estructura exacta:
   ```
   now-litoral/
   ├── README.md
   ├── scraper/
   │   ├── fuentes.json
   │   ├── requirements.txt
   │   └── verificar_fuentes.py
   └── .github/workflows/verificar-fuentes.yml
   ```
   Si el navegador no sube carpetas ocultas como `.github`, crea el archivo a mano:
   **Add file** -> **Create new file**, y en el nombre escribe `.github/workflows/verificar-fuentes.yml`
   (las barras crean las carpetas), pega el contenido y haz **Commit changes**.
3. Clic en **Commit changes**.

### 3. Ejecutar el verificador
1. Pestaña **Actions**. Si pide habilitar workflows, acepta.
2. A la izquierda: **Verificar fuentes** -> **Run workflow** -> **Run workflow**.
3. Espera unos minutos hasta que aparezca el tilde verde.
4. Abre la ejecucion: el informe aparece en el resumen. Tambien se descarga como
   `informe-fuentes` (al final de la pagina, en "Artifacts").

### 4. Que hacer con el resultado
Pasame el informe (captura o archivo `informe_fuentes.md`). Con eso se arma la lista real de fuentes.

## Estados del informe
- **OK**: feed valido con notas de las ultimas 48 h.
- **VIEJO**: feed valido pero sin notas recientes.
- **BLOQUEADO**: el sitio rechaza el pedido (403/429).
- **SIN FEED**: no se encontro ningun feed utilizable.

Este informe no evalua los terminos de uso de cada medio: eso se revisa a mano antes de integrar cada fuente.
