# DEVELOPED BY HARBEY CELY
# ESPERO ESTA HERRAMIENTA LES PUEDA AYUDAR A GESTIONAR CON MAYOR COMODIDAD SUS COLISIONES INTERDISCIPLINARIAS
# -*- coding: utf-8 -*-
"""Abre la ventana de revision en una interferencia ya marcada como resuelta."""
from __future__ import print_function

# Ver html_to_clash: la ventana no modal necesita el motor persistente.
__persistentengine__ = True

import os

from pyrevit import forms, revit

from clash_engine import load_last_report, load_session, read_collisions, save_last_report
from clash_review import choose_resolved_collision, open_review_window


def pick_report_path():
    """Ofrece usar el ultimo informe; si no, deja elegir otro."""
    last_report = load_last_report()
    if last_report:
        use_last = forms.alert(
            "Ultimo informe usado:\n{0}\n\nUsarlo? (No = elegir otro)".format(
                os.path.basename(last_report)
            ),
            title="Resolved Clashes",
            yes=True,
            no=True,
        )
        if use_last:
            return last_report
        if use_last is None:
            return None

    return forms.pick_file(file_ext="html", title="Seleccionar informe HTML")


def main():
    html_path = pick_report_path()
    if not html_path:
        return

    collisions = read_collisions(html_path)
    if not collisions:
        forms.alert(
            "No se encontraron interferencias en el HTML.",
            title="Informe no reconocido",
        )
        return

    resolved_flags = load_session(revit.doc, os.path.abspath(html_path), collisions)
    index = choose_resolved_collision(collisions, resolved_flags)
    if index is None:
        return

    save_last_report(html_path)
    open_review_window(revit.doc, collisions, index, html_path)


main()