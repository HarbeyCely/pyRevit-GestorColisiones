# DEVELOPED BY HARBEY CELY
# ESPERO ESTA HERRAMIENTA LES PUEDA AYUDAR A GESTIONAR CON MAYOR COMODIDAD SUS COLISIONES INTERDISCIPLINARIAS
# -*- coding: utf-8 -*-
"""Lee un informe HTML de interferencias y abre la ventana de revision."""
from __future__ import print_function

# La ventana no modal sigue viva al terminar el comando: pyRevit debe conservar
# el motor IronPython para que sus botones (ExternalEvent) respondan.
__persistentengine__ = True

from pyrevit import forms, revit

from clash_engine import read_collisions, save_last_report
from clash_review import choose_collision, open_review_window


def main():
    html_path = forms.pick_file(
        file_ext="html",
        title="Seleccionar informe HTML de colisiones",
    )
    if not html_path:
        return

    collisions = read_collisions(html_path)
    if not collisions:
        forms.alert(
            "No se encontraron dos IDs de elementos en el HTML.\n"
            "El informe debe contener los IDs de Revit de los dos elementos.",
            title="Informe no reconocido",
        )
        return

    start_index = choose_collision(collisions)
    if start_index is None:
        return

    save_last_report(html_path)
    open_review_window(revit.doc, collisions, start_index, html_path)


main()