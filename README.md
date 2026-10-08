# Gestor de Colisiones para Revit (pyRevit)

**Autor:** Harbey Cely | **Versión:** v1.0.0

Un flujo de trabajo avanzado para la revisión de interferencias en modelos BIM. Este plugin lee los informes HTML nativos de Revit y genera un entorno de revisión interactivo y no modal, permitiendo a los ingenieros y coordinadores aislar, verificar geométricamente y gestionar el estado de las colisiones sin interrumpir el uso de las herramientas de modelado.

---

## 1. Características Principales

- **Lectura nativa sin dependencias:** Procesa el HTML de Revit mediante expresiones regulares puras.
- **Ventana de revisión No Modal:** Interfaz persistente que permite orbitar, hacer zoom y editar el modelo mientras se inspeccionan las colisiones.
- **Seccionamiento dinámico:** Genera automáticamente un *Section Box* en la vista 3D ("Clash Review") calculado a partir de la *BoundingBox* combinada de los elementos en conflicto.
- **Doble verificación (Filtro Geométrico):** Utiliza la API de Revit (`ElementIntersectsElementFilter`) para confirmar si la intersección geométrica persiste en el estado actual del modelo.
- **Persistencia de datos:** Guarda el estado de revisión (colisiones resueltas) en tiempo real mediante archivos `.json`.

## 2. Requisitos del Sistema

- **Revit 2024 o superior** (Desarrollado y testeado en Revit 2027). *Nota: El script utiliza identificadores `ElementId` con `Int64`, por lo que no es retrocompatible con versiones antiguas.*
- **pyRevit** instalado, utilizando el motor IronPython predeterminado.
- El informe HTML debe revisarse sobre el **mismo modelo** con el que fue generado. (Modelo de prueba utilizado: *Snowdon Towers Sample Architectural.rvt*).

## 3. Estructura del Proyecto

El bundle está estructurado bajo los estándares de pyRevit. El núcleo lógico se encuentra encapsulado en la carpeta `lib/` para mantener limpios los scripts de ejecución.

```text
GestorColisiones/
├── GestorColisiones.extension/
│   ├── lib/
│   │   ├── clash_engine.py      # Lógica core: regex, BoundingBox, filtros, JSON.
│   │   └── clash_review.py      # Interfaz gráfica no modal compartida.
│   └── GestorColisiones.tab/
│       └── clashdetectiveLIVE.panel/
│           ├── html_to_clash.pushbutton/    # Script, UI y metadatos
│           └── resolved_clashes.pushbutton/ # Script, UI y metadatos
├── reporte_interferencias/      # HTML de ejemplo (6119 colisiones)
├── memoria/                     # Backup del session.json generado
└── README.md
```

## 4. Instalación

1. Copia la carpeta `GestorColisiones.extension` a tu directorio de extensiones de pyRevit:
   `%APPDATA%\pyRevit\Extensions\` (o la ruta personalizada que hayas configurado).
2. En Revit, dirígete a la pestaña de **pyRevit** y haz clic en **Reload**.
3. Aparecerá una nueva pestaña llamada **GestorColisiones** con las herramientas operativas.

## 5. Generación del Informe en Revit

Para que el plugin funcione correctamente, el informe base debe generarse desde la herramienta nativa de Revit:

1. Ir a `Collaborate` > `Coordinate` > `Interference Check` > `Run Interference Check`.
2. Seleccionar las categorías o vínculos a comparar.
3. En la ventana de resultados, seleccionar **Export...** y guardar el archivo en formato `.html`.

*(El parser del plugin identifica las filas mediante el estándar "id NNNNNN" al final de la descripción).*

## 6. Guía de Uso

### Botón "HTML to Clash" (Nueva Revisión)

1. Carga el archivo `.html` exportado previamente.
2. Selecciona la colisión inicial desde el buscador integrado de pyRevit (`SelectFromList`).
3. Se abrirá la interfaz flotante y Revit encuadrará automáticamente la vista 3D.

### Navegación en la Ventana de Revisión

La ventana flotante incluye los siguientes controles en tiempo real:

- **Anterior / Siguiente:** Navegación secuencial por el informe.
- **Aislar elementos / Mostrar todo:** Aísla temporalmente la pareja de elementos en conflicto.
- **Marcar / Desmarcar como resuelta:** Actualiza instantáneamente el registro `.json`.
- **Ver resueltas (n) / Ir a...:** Accesos directos para saltar a colisiones específicas.
- **Quitar selección:** Libera la selección de Revit para visualizar correctamente los colores de inspección (Elemento A en **Rojo**, Elemento B en **Naranja**).

### Botón "Resolved Clashes" (Auditoría)

Permite retomar el trabajo visualizando únicamente los conflictos que el equipo ha marcado como resueltos en el informe actual o cargar un histórico distinto.

## 7. Criterios de Verificación y Encuadre 3D

El plugin separa el registro histórico (HTML) de la comprobación geométrica actual. La *Section Box* es estrictamente una ayuda visual, mientras que la confirmación matemática recae en la API.

**Estados devueltos por el filtro:**

- `CONFIRMADA`: Intersección geométrica comprobada en el modelo actual.
- `NO_CONFIRMADA`: Elementos presentes, pero sin intersección actual (posible resolución post-informe).
- `VINCULOS`: Elementos en documentos distintos (Host/Link); requiere revisión visual.
- `ERROR`: Categoría no soportada por el filtro geométrico.
- `NO_APLICA`: Registro del informe corrupto o con elementos faltantes.

## 8. Persistencia de Datos (JSON)

El estado de la revisión se guarda localmente en:

`%APPDATA%\pyRevit\ClashReview\session.json`

El esquema agrupa las resoluciones asegurando que los informes no se mezclen:

```json
{
  "C:/ruta/modelo.rvt||C:/ruta/informe.html": {
    "resolved": {
      "123456|654321": true
    }
  }
}
```

*Si los archivos originales se mueven o renombran, el sistema asume el inicio de una nueva sesión de auditoría.*

## 9. Notas Técnicas y Limitaciones

- **Vínculos:** Por limitaciones de la API, el resaltado de color aísla la instancia completa del vínculo, no el sub-elemento.
- **Codificación:** El motor IronPython 2.7 es sensible a los caracteres no ASCII. Los módulos en `.py` están redactados evitando tildes para garantizar la máxima estabilidad.
- **Limpieza:** La vista "Clash Review" y las modificaciones visuales permanecen en el archivo `.rvt`. Elimine la vista para limpiar los *overrides*.
- **Ejecución persistente:** El plugin requiere que el flag `__persistentengine__ = True` esté declarado en la cabecera de los scripts para que la interfaz mantenga el hilo de ejecución activo.

## 10. Solución de Problemas (Troubleshooting)

- **"Revit could not complete the external command":** Generalmente se debe a un carácter no ASCII (como tildes o eñes) en un archivo `.py` sin declaración de codificación, o un error de importación (ej. `clash_engine.py` no está en la carpeta `lib/`). Revisa el log de errores de pyRevit en `%APPDATA%\pyRevit\`.
- **Los botones de la ventana no responden:** Revisa la línea de estado inferior de la ventana. Si se queda colgada en "Procesando...", cierra la ventana, ejecuta un *Reload* en la pestaña de pyRevit y vuelve a lanzar la herramienta.
- **No se ven los colores de inspección:** Haz clic en el botón "Quitar selección" en la interfaz. El resaltado azul de selección predeterminado de Revit a menudo se superpone y oculta los colores de advertencia.
- **"Informe no reconocido":** El archivo HTML exportado no contiene el texto requerido (`id NNNNNN`) en la descripción de los elementos. Vuelve a exportarlo asegurándote de usar estrictamente la herramienta *Interference Check* nativa de Revit.
