import unittest
import pytest

from planet_explorer.tests.utils import qgis_debug_wait
from qgis.PyQt import QtCore
from planet_explorer.gui.pe_tasking_dockwidget import WarningDialog
from qgis.PyQt.QtWidgets import QTextBrowser

pytestmark = [pytest.mark.qgis_show_map(add_basemap=False, timeout=1)]


class TestTaskingWidget(unittest.TestCase):
    def test_tasking_widget(
        self,
        qtbot,
        logged_in_explorer_dock_widget,
        qgis_debug_enabled,
        sample_aoi,
        tasking_widget,
        qgis_canvas,
        qgis_version,
    ):
        """
        Verifies:
            - PLQGIS-TC09
        """
        dock_widget = logged_in_explorer_dock_widget()
        task_dockwidget = tasking_widget(dock_widget)
        dock_widget.hide()

        # click the 'Selection' button
        qtbot.mouseClick(task_dockwidget.btnMapTool, QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        self.assertTrue(task_dockwidget.btnCancel.isEnabled())
        self.assertFalse(task_dockwidget.btnOpenDashboard.isEnabled())

        # click some point on the canvas
        qtbot.mouseClick(qgis_canvas.viewport(), QtCore.Qt.LeftButton)
        qgis_debug_wait(qtbot, qgis_debug_enabled)

        if qgis_version > 32000:
            self.assertTrue(task_dockwidget.btnCancel.isEnabled())
            self.assertTrue(task_dockwidget.btnOpenDashboard.isEnabled())
            self.assertIn(
                "Selected Point Coordinates",
                task_dockwidget.textBrowserPoint.toPlainText(),
            )

            # make sure the dialog appears
            dialog = WarningDialog(task_dockwidget.pt)

            def _dialog_interact():
                text_browser = [
                    widget
                    for widget in dialog.children()
                    if isinstance(widget, QTextBrowser)
                ][0]
                self.assertTrue(
                    text_browser.toPlainText(), "No text displayed in dialog!"
                )
                dialog.close()

            QtCore.QTimer.singleShot(1000, _dialog_interact)
            task_dockwidget._open_tasking_dashboard(dlg=dialog)
