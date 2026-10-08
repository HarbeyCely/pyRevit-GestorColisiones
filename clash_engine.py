# DEVELOPED BY HARBEY CELY
# ESPERO ESTA HERRAMIENTA LES PUEDA AYUDAR A GESTIONAR CON MAYOR COMODIDAD SUS COLISIONES INTERDISCIPLINARIAS
from __future__ import print_function
import System
import re
import json
import os

from Autodesk.Revit import DB


ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
CELL_PATTERN = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
ID_TOKEN_PATTERN = re.compile(r"\bid\s+(\d+)\b", re.I)


def _clean_text(html_fragment):
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    return " ".join(text.split())


def _label_and_id(cell_text):
    match = ID_TOKEN_PATTERN.search(cell_text)
    if not match:
        return None
    element_id = int(match.group(1))
    if element_id <= 0:
        return None
    label = cell_text[:match.start()].strip(" :\t")
    return label, element_id

# Lectura de informe de colisiones
def read_collisions(path):
    with open(path, "r") as html_file:
        content = html_file.read()

    collisions = []
    for row_html in ROW_PATTERN.findall(content):
        cells = [_clean_text(cell) for cell in CELL_PATTERN.findall(row_html)]
        parsed = [item for item in (_label_and_id(cell) for cell in cells) if item]
        if len(parsed) == 2:
            (label_a, id_a), (label_b, id_b) = parsed
            collisions.append({
                "name": "{0}   <->   {1}".format(label_a, label_b),
                "ids": [id_a, id_b],
                "index": len(collisions) + 1,
            })

    if collisions:
        return collisions

    # Si no se encontraron filas con el metodo anterior, se intenta
    # extraer los IDs de otra manera, buscando todos los numeros de ID
    text_only = _clean_text(content)
    ids_found = [int(value) for value in ID_TOKEN_PATTERN.findall(text_only) if int(value) > 0]
    for start in range(0, len(ids_found) - 1, 2):
        pair = ids_found[start:start + 2]
        collisions.append({
            "name": "Colision {0}: IDs {1} y {2}".format(len(collisions) + 1, pair[0], pair[1]),
            "ids": pair,
            "index": len(collisions) + 1,
        })
    return collisions


def _link_instances(document):
    collector = DB.FilteredElementCollector(document)
    return list(collector.OfClass(DB.RevitLinkInstance))

# revisa si un elemento existe en el RVT anfitrion o en alguno de los vinculos, y devuelve
# informacion sobre el elemento y su transformacion
def resolve_element(document, element_id):
    host_element = document.GetElement(DB.ElementId(System.Int64(element_id)))
    if host_element is not None:
        return {
            "element": host_element,
            "document": document,
            "transform": DB.Transform.Identity,
            "source": "anfitrion",
            "selection_id": host_element.Id,
        }

    for link_instance in _link_instances(document):
        link_document = link_instance.GetLinkDocument()
        if link_document is None:
            continue
        linked_element = link_document.GetElement(DB.ElementId(System.Int64(element_id)))
        if linked_element is not None:
            return {
                "element": linked_element,
                "document": link_document,
                "transform": link_instance.GetTransform(),
                "source": "vinculo: {0}".format(link_document.Title),
                "selection_id": link_instance.Id,
            }
    return None

# Generacion de 8 puntos de esquina del bounding box de cada elemento, en coordenadas
def _world_points( bounding_box, transform):
    if bounding_box is None:
        return []
    minimum = bounding_box.Min
    maximum = bounding_box.Max
    points = []
    for x in (minimum.X, maximum.X):
        for y in (minimum.Y, maximum.Y):
            for z in (minimum.Z, maximum.Z):
                points.append(transform.OfPoint(DB.XYZ(x, y, z)))
    return points

# Calcula limites del bounding box de los elementos
def _bounds_for(resolved):
    element = resolved["element"]
    points = _world_points(element.get_BoundingBox(None), resolved["transform"])
    if not points:
        return None
    return min(point.X for point in points), max(point.X for point in points), min(
        point.Y for point in points
    ), max(point.Y for point in points), min(point.Z for point in points), max(
        point.Z for point in points
    )

# combina las cajas de los 2 elementos de la colision, con un padding (separacion) del 15% del de mayor dimension
def combined_bounds(resolved_elements):
    bounds = [_bounds_for(item) for item in resolved_elements]
    bounds = [item for item in bounds if item is not None]
    if not bounds:
        return None

    padding = max(
        0.5,
        max(
            max(item[1] - item[0], item[3] - item[2], item[5] - item[4])
            for item in bounds
        )
        * 0.15,
    )
    section_box = DB.BoundingBoxXYZ()
    section_box.Min = DB.XYZ(
        min(item[0] for item in bounds) - padding,
        min(item[2] for item in bounds) - padding,
        min(item[4] for item in bounds) - padding,
    )
    section_box.Max = DB.XYZ(
        max(item[1] for item in bounds) + padding,
        max(item[3] for item in bounds) + padding,
        max(item[5] for item in bounds) + padding,
    )
    return section_box


def _solid_fill_pattern_id(document):
    collector = DB.FilteredElementCollector(document).OfClass(DB.FillPatternElement)
    for pattern_element in collector:
        pattern = pattern_element.GetFillPattern()
        if pattern.IsSolidFill and pattern.Target == DB.FillPatternTarget.Drafting:
            return pattern_element.Id
    return DB.ElementId.InvalidElementId


def build_color_override(document, color):
    settings = DB.OverrideGraphicSettings()
    settings.SetProjectionLineColor(color)
    settings.SetProjectionLineWeight(6)
    settings.SetCutLineColor(color)
    settings.SetCutLineWeight(6)

    solid_fill_id = _solid_fill_pattern_id(document)
    if solid_fill_id != DB.ElementId.InvalidElementId:
        settings.SetSurfaceForegroundPatternColor(color)
        settings.SetSurfaceForegroundPatternId(solid_fill_id)
        settings.SetSurfaceForegroundPatternVisible(True)
        settings.SetCutForegroundPatternColor(color)
        settings.SetCutForegroundPatternId(solid_fill_id)
        settings.SetCutForegroundPatternVisible(True)
    return settings


def clear_overrides(view, element_ids):
    empty = DB.OverrideGraphicSettings()
    for element_id in element_ids:
        view.SetElementOverrides(element_id, empty)

# ----------------------------------------------------------------------
# Persistencia de estado de revision
# ----------------------------------------------------------------------

def _session_file_path():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.expanduser("~")

    folder = os.path.join(appdata, "pyRevit", "ClashReview")

    if not os.path.exists(folder):
        os.makedirs(folder)

    return os.path.join(folder, "session.json")


def _document_key(document):
    try:
        path = document.PathName
    except Exception:
        path = ""

    if path:
        return os.path.abspath(path)

    return document.Title


def _collision_key(collision):
    ids = sorted([int(value) for value in collision["ids"]])
    return "{0}|{1}".format(ids[0], ids[1])

# compara el estado de resolucion de las colisiones guardado en la sesion (informe html) 
# con el estado actual de los elementos en el modelo.
# si un elemento ya no existe, se marca como no resuelto
def load_session(document, source_path, collisions):
    session_path = _session_file_path()

    try:
        with open(session_path, "r") as json_file:
            data = json.load(json_file)
    except Exception:
        data = {}

    document_key = _document_key(document)
    report_key = os.path.abspath(source_path)
    session_key = "{0}||{1}".format(document_key, report_key)

    saved = data.get(session_key, {})
    saved_resolved = saved.get("resolved", {})

    resolved_flags = []

    for collision in collisions:
        key = _collision_key(collision)
        resolved_flags.append(bool(saved_resolved.get(key, False)))

    return resolved_flags

# escribe la informacion de la interferencia en el JSON
def save_session(document, source_path, collisions, resolved_flags):
    session_path = _session_file_path()

    try:
        with open(session_path, "r") as json_file:
            data = json.load(json_file)
    except Exception:
        data = {}

    document_key = _document_key(document)
    report_key = os.path.abspath(source_path)
    session_key = "{0}||{1}".format(document_key, report_key)

    resolved = {}

    for collision, flag in zip(collisions, resolved_flags):
        resolved[_collision_key(collision)] = bool(flag)

    data[session_key] = {
        "resolved": resolved,
    }

    with open(session_path, "w") as json_file:
        json.dump(data, json_file, indent=4)


# ----------------------------------------------------------------------
# Verificacion geometrica
# ----------------------------------------------------------------------

# verificacion real de las interferencias
def verify_collision(resolved_elements):
    if len(resolved_elements) != 2:
        return {
            "status": "NO_APLICA",
            "message": "La colision no contiene exactamente dos elementos.",
        }

    first = resolved_elements[0]
    second = resolved_elements[1]

    # ElementIntersectsElementFilter trabaja directamente entre
    # elementos del mismo documento.
    if first["document"] != second["document"]:
        return {
            "status": "VINCULOS",
            "message": (
                "No verificable directamente con "
                "ElementIntersectsElementFilter: los elementos "
                "pertenecen a documentos distintos."
            ),
        }

    try:
        intersection_filter = DB.ElementIntersectsElementFilter(
            first["element"]
        )

        intersects = intersection_filter.PassesFilter(second["element"])

        if intersects:
            return {
                "status": "CONFIRMADA",
                "message": "Interseccion confirmada por Revit.",
            }

        return {
            "status": "NO_CONFIRMADA",
            "message": (
                "La interseccion no fue confirmada por "
                "ElementIntersectsElementFilter."
            ),
        }

    except Exception as error:
        return {
            "status": "ERROR",
            "message": (
                "No se pudo ejecutar ElementIntersectsElementFilter: "
                "{0}".format(error)
            ),
        }

def get_resolved_collisions(document, source_path, collisions):
    resolved_flags = load_session(
        document,
        source_path,
        collisions,
    )

    return [
        collision
        for collision, resolved in zip(collisions, resolved_flags)
        if resolved
    ]


# ----------------------------------------------------------------------
# Ultimo informe usado (para el boton Resolved Clashes)
# ----------------------------------------------------------------------

def _last_report_path():
    return os.path.join(os.path.dirname(_session_file_path()), "last_report.txt")


def save_last_report(source_path):
    """ Recuerda el ultimo informe HTML abierto."""
    with open(_last_report_path(), "w") as text_file:
        text_file.write(os.path.abspath(source_path))


def load_last_report():
    """Devuelve la ruta del ultimo informe usado, o None si ya no existe."""
    try:
        with open(_last_report_path(), "r") as text_file:
            path = text_file.read().strip()
    except Exception:
        return None
    if path and os.path.isfile(path):
        return path
    return None