# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QCoreApplication, QThread, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextEdit,
    QVBoxLayout,
)

from ..pe_utils import open_link_with_browser
from ..planet_api.p_client import PlanetClient


class LoginWorker(QThread):
    """Runs the blocking login completion check in a background thread."""

    finished_signal = pyqtSignal(bool, str)

    def __init__(self, p_client, login_info=None, token_exists=False):
        super().__init__()
        self.p_client = p_client
        self.login_info = login_info
        self.token_exists = token_exists

    def run(self):
        if self.token_exists:
            built_engines = self.p_client.build_engines()
            if built_engines:
                self.finished_signal.emit(True, "Success")
            else:
                self.finished_signal.emit(
                    False, "Token exists but failed to initialize client!"
                )
        else:
            try:
                self.p_client.complete_log_in(self.login_info)
                self.finished_signal.emit(True, "Success")
            except Exception as e:
                self.finished_signal.emit(False, str(e))


class PlanetAuthenticationDialog(QDialog):

    def __init__(self, parent=None):
        super(PlanetAuthenticationDialog, self).__init__(parent)

        self.setWindowTitle("Planet Authentication")
        self.resize(450, 300)

        self.layout = QVBoxLayout(self)

        self.log_box = QTextEdit(self)
        self.log_box.setReadOnly(True)
        self.layout.addWidget(self.log_box)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("Ok")
        self.layout.addWidget(self.button_box)

        self.cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.p_client = None
        self.worker = None
        self.workflow_started = False

    def showEvent(self, event):
        super().showEvent(event)
        if self.p_client is None:
            self.p_client = PlanetClient.getInstance()

        if not self.workflow_started:
            self.workflow_started = True
            self.setup_client_workflow()

    def setup_client_workflow(self):
        self.p_client.get_auth_context()
        if self.p_client.auth_is_valid():
            self.setup_client_with_token()
        else:
            self.setup_client_device_user_workflow()

    def setup_client_with_token(self):
        try:
            self.ok_button.setEnabled(False)

            self.log_box.setText("--- Planet Authentication Complete ---\n")
            self.log_box.append("User already logged in!\n")
            QCoreApplication.processEvents()

            self.worker = LoginWorker(self.p_client, token_exists=True)
            self.worker.finished_signal.connect(self.handle_login_finished)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.start()

        except Exception as e:
            self.log_box.setText(f"Login failed:\n{str(e)}")
            self.ok_button.setEnabled(True)
            self.ok_button.setText("Close")

    def setup_client_device_user_workflow(self):
        """Triggered ONLY if the background validation thread fails."""
        try:
            self.ok_button.setEnabled(False)

            auth = self.p_client.auth
            login_info = auth.device_user_login_initiate()

            user_code = login_info.get("user_code", "ERROR")
            url = login_info.get("verification_uri_complete") or login_info.get(
                "verification_uri"
            )

            self.log_box.setText("--- Planet Authentication Required ---\n")
            self.log_box.append(f"Authorization Code: {user_code}\n")
            self.log_box.append(
                "Opening browser link... Please click confirm in your browser."
            )
            self.log_box.append("\nWaiting for browser confirmation...")

            QCoreApplication.processEvents()
            open_link_with_browser(url)

            self.worker = LoginWorker(self.p_client, login_info)
            self.worker.finished_signal.connect(self.handle_login_finished)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.start()

        except Exception as e:
            self.log_box.setText(f"Login failed:\n{str(e)}")
            self.ok_button.setEnabled(True)
            self.ok_button.setText("Close")

    def handle_login_finished(self, success, message):
        if success:
            self.log_box.append("\n[SUCCESS] Login Complete!")
            self.ok_button.setText("Ok")
            self.ok_button.setEnabled(True)
            self.cancel_button.setVisible(False)

            if self.p_client:
                self.p_client.loginChanged.emit(True)

            QTimer.singleShot(1500, self.accept)
        else:
            self.log_box.append(f"\n[ERROR] Failed: {message}")
            self.ok_button.setEnabled(True)
            self.ok_button.setText("Close")

    def closeEvent(self, event):
        # Ensure the background thread terminates if the
        # window is closed early
        if self.worker and self.worker.isRunning():
            try:
                self.worker.finished_signal.disconnect(self.handle_login_finished)
            except TypeError:
                pass
            self.worker.terminate()
            self.worker.wait()
        super().closeEvent(event)
