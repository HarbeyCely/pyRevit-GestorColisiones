# DEVELOPED BY HARBEY CELY
# ESPERO ESTA HERRAMIENTA LES PUEDA AYUDAR A GESTIONAR CON MAYOR COMODIDAD SUS COLISIONES INTERDISCIPLINARIAS
# -*- coding: utf-8 -*-
"""Ventana de revision no modal y utilidades compartidas por los botones."""
from __future__ import print_function

import os

from Autodesk.Revit import DB
from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler
from pyrevit import forms, revit
from System.Collections.Generic import List
from System.Windows import SystemParameters

from clash_engine import (
    build_color_override,
    clear_overrides,
    combined_bounds,
    load_session,
    resolve_element,
    save_session,
    verify_collision,
)

CLASH_VIEW_NAME = "Clash Review"
COLOR_A = DB.Color(230, 60, 60)
COLOR_B = DB.Color(240, 140, 40)

# INTERFAZ DECLARATIVA
WINDOW_XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Revision de colisiones" Width="700" Height="340"
        MinWidth="460" MinHeight="260" ShowInTaskbar="False"
        ResizeMode="CanResizeWithGrip" WindowStartupLocation="Manual"
        Closed="window_closed">
    <Grid Margin="10">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>
        <TextBlock x:Name="header_text" Grid.Row="0" FontSize="15"
                   FontWeight="Bold" TextWrapping="Wrap"/>
        <ScrollViewer Grid.Row="1" Margin="0,8,0,8" VerticalScrollBarVisibility="Auto">
            <TextBlock x:Name="detail_text" TextWrapping="Wrap"/>
        </ScrollViewer>
        <TextBlock x:Name="status_text" Grid.Row="2" Margin="0,0,0,6"
                   Foreground="Gray" FontSize="11" TextWrapping="Wrap"/>
        <WrapPanel Grid.Row="3">
            <Button x:Name="prev_button" Content="&lt; Anterior" Click="prev_click"
                    Margin="0,0,6,6" Padding="10,4"/>
            <Button x:Name="next_button" Content="Siguiente &gt;" Click="next_click"
                    Margin="0,0,6,6" Padding="10,4"/>
            <Button x:Name="isolate_button" Content="Aislar elementos" Click="isolate_click"
                    Margin="0,0,6,6" Padding="10,4"/>
            <Button x:Name="resolve_button" Content="Marcar como resuelta" Click="resolve_click"
                    Margin="0,0,6,6" Padding="10,4"/>
            <Button x:Name="resolved_button" Content="Ver resueltas" Click="resolved_list_click"
                    Margin="0,0,6,6" Padding="10,4"/>
            <Button x:Name="goto_button" Content="Otra seleccion..." Click="goto_click"
                    Margin="0,0,6,6" Padding="10,4"/>
            <Button x:Name="deselect_button" Content="Quitar seleccion" Click="deselect_click"
                    Margin="0,0,6,6" Padding="10,4"/>
            <Button x:Name="close_button" Content="Cerrar" Click="close_click"
                    Margin="0,0,6,6" Padding="10,4"/>
        </WrapPanel>
    </Grid>
</Window>
"""


def get_3d_view(document):
    """Devuelve la vista 3D 'Clash Review'; la crea si no existe."""
    views = DB.FilteredElementCollector(document).OfClass(DB.View3D)
    for view in views:
        if not view.IsTemplate and view.Name == CLASH_VIEW_NAME:
            return view

    view_type = next(
        view_type
        for view_type in DB.FilteredElementCollector(document).OfClass(DB.ViewFamilyType)
        if view_type.ViewFamily == DB.ViewFamily.ThreeDimensional
    )
    with revit.Transaction("Crear vista Clash Review"):
        new_view = DB.View3D.CreateIsometric(document, view_type.Id)
        try:
            new_view.Name = CLASH_VIEW_NAME
        except Exception:
            pass
        return new_view


def frame_collision(document, resolved_elements, view):
    """Ajusta el Section Box de la vista a la caja combinada de los elementos."""
    section_box = combined_bounds(resolved_elements)
    if section_box is None:
        raise RuntimeError("No se encontro una caja geometrica para los elementos.")

    with revit.Transaction("Encuadrar colision"):
        view.IsSectionBoxActive = True
        view.SetSectionBox(section_box)

    revit.uidoc.ActiveView = view
    for ui_view in revit.uidoc.GetOpenUIViews():
        if ui_view.ViewId == view.Id:
            ui_view.ZoomAndCenterRectangle(section_box.Min, section_box.Max)
            break


def _pick_from_list(options, title, button_name):
    """Muestra una lista con buscador y devuelve el indice elegido (o None)."""
    longest = max(len(text) for text in options)
    window_width = min(1400, max(500, longest * 7 + 120))
    selected = forms.SelectFromList.show(
        options,
        title=title,
        width=window_width,
        height=700,
        multiselect=False,
        button_name=button_name,
    )
    if not selected:
        return None
    return options.index(selected)


def choose_collision(collisions):
    """Selector de cualquier colision del informe. Devuelve su posicion."""
    if len(collisions) == 1:
        return 0
    options = ["{0}: {1}".format(item["index"], item["name"]) for item in collisions]
    return _pick_from_list(options, "Seleccionar colision", "Encuadrar")


def choose_resolved_collision(collisions, resolved_flags):
    """Selector solo de las colisiones marcadas como resueltas."""
    resolved_indices = [index for index, flag in enumerate(resolved_flags) if flag]
    if not resolved_indices:
        forms.alert(
            "No hay interferencias marcadas como resueltas.",
            title="Sin interferencias resueltas",
        )
        return None

    options = [
        "{0}: {1}".format(collisions[index]["index"], collisions[index]["name"])
        for index in resolved_indices
    ]
    picked = _pick_from_list(options, "Interferencias resueltas", "Abrir")
    if picked is None:
        return None
    return resolved_indices[picked]


class ActionHandler(IExternalEventHandler):
    """Ejecuta dentro del contexto de la API de Revit las acciones en cola."""

    def __init__(self, report):
        self.actions = []
        self.report = report

    def Execute(self, uiapp):
        while self.actions:
            action = self.actions.pop(0)
            try:
                action()
                self.report("Listo.")
            except Exception as error:
                self.report("Error: {0}".format(error))

    def GetName(self):
        return "ClashReviewActionHandler"


class ReviewWindow(forms.WPFWindow):
    """Ventana no modal: permite usar las herramientas de Revit mientras esta abierta."""

    def __init__(self, document, collisions, start_index, source_path):
        forms.WPFWindow.__init__(self, WINDOW_XAML, literal_string=True, handle_esc=False)

        self.document = document
        self.collisions = collisions  # todas las colisiones del informe
        self.index = start_index  # colision actual
        self.source_path = os.path.abspath(source_path)
        self.resolved_flags = load_session(document, self.source_path, collisions)  # memoriza estado
        self.view = get_3d_view(document)
        self.highlighted_ids = []   # elementos con los colores nuevos aplicados
        self.current_ids = []   # elementos actuales
        self.isolate_active = False  # aislamiento on/off

        self.action_handler = ActionHandler(self.set_status)
        self.action_event = ExternalEvent.Create(self.action_handler)

        self.Title = "Revision de colisiones - {0}".format(os.path.basename(self.source_path))

    # ------------------------------------------------------------------
    # Eventos de la ventana (hilo de interfaz): solo ponen acciones en cola
    # ------------------------------------------------------------------
    def set_status(self, text):
        self.status_text.Text = text

    def queue(self, action):
        self.set_status("Procesando...")
        try:
            self.action_handler.actions.append(action)
            self.action_event.Raise()
        except Exception as error:
            self.set_status("Error al enviar la accion: {0}".format(error))

    def prev_click(self, sender, args):
        self.queue(self.go_previous)

    def next_click(self, sender, args):
        self.queue(self.go_next)

    def isolate_click(self, sender, args):
        self.queue(self.toggle_isolation)

    def resolve_click(self, sender, args):
        self.queue(self.toggle_resolved)

    def resolved_list_click(self, sender, args):
        self.queue(self.open_resolved_list)

    def goto_click(self, sender, args):
        self.queue(self.open_goto_list)

    def deselect_click(self, sender, args):
        self.queue(self.clear_selection)

    def close_click(self, sender, args):
        self.Close()

    def window_closed(self, sender, args):
        self.queue(self.clear_isolation)

    # ------------------------------------------------------------------
    # Acciones (contexto API de Revit)
    # ------------------------------------------------------------------
    def go_previous(self):
        if self.index > 0:
            self.index -= 1
            self.show_current()

    def go_next(self):
        if self.index < len(self.collisions) - 1:
            self.index += 1
            self.show_current()

    def toggle_isolation(self):
        if self.isolate_active:
            self.clear_isolation()
        else:
            self.isolate_active = True
            self.apply_isolation()
        self.refresh_buttons()

    def toggle_resolved(self):
        self.resolved_flags[self.index] = not self.resolved_flags[self.index]
        save_session(self.document, self.source_path, self.collisions, self.resolved_flags)
        self.refresh_header()
        self.refresh_buttons()

    def open_resolved_list(self):
        picked = choose_resolved_collision(self.collisions, self.resolved_flags)
        if picked is not None:
            self.index = picked
            self.show_current()

    def open_goto_list(self):
        picked = choose_collision(self.collisions)
        if picked is not None:
            self.index = picked
            self.show_current()

    def clear_selection(self):
        revit.uidoc.Selection.SetElementIds(List[DB.ElementId]())

    def apply_isolation(self):
        if self.isolate_active and self.current_ids:
            with revit.Transaction("Aislar colision"):
                self.view.IsolateElementsTemporary(List[DB.ElementId](self.current_ids))

    def clear_isolation(self):
        if self.isolate_active:
            with revit.Transaction("Quitar aislamiento"):
                if self.view.IsInTemporaryViewMode(DB.TemporaryViewMode.TemporaryHideIsolate):
                    self.view.DisableTemporaryViewMode(DB.TemporaryViewMode.TemporaryHideIsolate)
            self.isolate_active = False

    def clear_current_highlight(self):
        if self.highlighted_ids:
            with revit.Transaction("Limpiar resaltado"):
                clear_overrides(self.view, self.highlighted_ids)
            del self.highlighted_ids[:]

    def paint_elements(self, resolved_elements):
        with revit.Transaction("Resaltar colision"):
            for item, color in zip(resolved_elements, [COLOR_A, COLOR_B]):
                override = build_color_override(self.document, color)
                self.view.SetElementOverrides(item["selection_id"], override)
                self.highlighted_ids.append(item["selection_id"])

    def show_current(self):
        """Resuelve, verifica, encuadra y pinta la colision actual."""
        collision = self.collisions[self.index]
        resolved_elements = [
            resolve_element(self.document, element_id) for element_id in collision["ids"]
        ]
        missing = [
            str(element_id)
            for element_id, item in zip(collision["ids"], resolved_elements)
            if item is None
        ]

        self.clear_current_highlight()
        self.current_ids = []

        if missing:
            lines = [
                collision["name"],
                "",
                "Origen del registro: informe HTML de interferencias de Revit.",
                "IDs reportados: {0} y {1}".format(collision["ids"][0], collision["ids"][1]),
                "",
                "Verificacion geometrica: NO DISPONIBLE",
                "Aviso: no se encontraron en el documento activo los IDs: {0}.".format(
                    ", ".join(missing)
                ),
                "Comprueba que el modelo anfitrion y sus vinculos esten cargados.",
                "",
                "Encuadre 3D: no generado porque faltan elementos.",
            ]
        else:
            verification = verify_collision(resolved_elements)
            lines = [
                collision["name"],
                "",
                "Origen del registro: informe HTML de interferencias de Revit.",
                "Elemento A: ID {0} - {1}".format(
                    collision["ids"][0], resolved_elements[0]["source"]
                ),
                "Elemento B: ID {0} - {1}".format(
                    collision["ids"][1], resolved_elements[1]["source"]
                ),
                "",
                "Verificacion geometrica: {0}".format(verification["status"]),
                "Detalle: {0}".format(verification["message"]),
                "",
                "Encuadre 3D: BoundingBox combinada utilizada solo para facilitar la inspeccion visual.",
            ]

            try:
                frame_collision(self.document, resolved_elements, self.view)
                self.paint_elements(resolved_elements)
                self.current_ids = list(set(item["selection_id"] for item in resolved_elements))
                self.apply_isolation()
                revit.uidoc.Selection.SetElementIds(List[DB.ElementId](self.current_ids))
            except Exception as error:
                lines[-1] = "Encuadre 3D: no se pudo generar el encuadre. {0}".format(error)

        self.detail_text.Text = "\n".join(lines)
        self.refresh_header()
        self.refresh_buttons()

    # ------------------------------------------------------------------
    # Actualizacion de textos y botones
    # ------------------------------------------------------------------
    def refresh_header(self):
        status = "RESUELTA" if self.resolved_flags[self.index] else "pendiente"
        self.header_text.Text = "Colision {0} de {1}  [{2}]".format(
            self.index + 1, len(self.collisions), status
        )

    def refresh_buttons(self):
        resolved_count = sum(1 for flag in self.resolved_flags if flag)
        self.prev_button.IsEnabled = self.index > 0
        self.next_button.IsEnabled = self.index < len(self.collisions) - 1
        self.isolate_button.Content = "Mostrar todo" if self.isolate_active else "Aislar elementos"
        self.resolve_button.Content = (
            "Desmarcar resuelta" if self.resolved_flags[self.index] else "Marcar como resuelta"
        )
        self.resolved_button.Content = "Ver resueltas ({0})".format(resolved_count)
        self.resolved_button.IsEnabled = resolved_count > 0


def open_review_window(document, collisions, start_index, source_path):
    """Crea la ventana no modal, encuadra la primera colision y la muestra."""
    window = ReviewWindow(document, collisions, start_index, source_path)
    window.show_current()

    work_area = SystemParameters.WorkArea
    window.Left = work_area.Right - window.Width - 20
    window.Top = work_area.Bottom - window.Height - 20
    window.Show()