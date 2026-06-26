# -*- coding: utf-8 -*-
import shutil

from qgis.PyQt.QtCore import QCoreApplication, QThread, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
)

from ..pe_utils import open_link_with_browser
from ..planet_api.p_client import PlanetClient


class LoginWorker(QThread):
    """Runs the blocking login completion check in a background thread."""

    finished_signal = pyqtSignal(bool, str)

    def __init__(
        self, p_client, login_info=None, token_exists=False, clean_session=False
    ):
        super().__init__()
        self.p_client = p_client
        self.login_info = login_info
        self.token_exists = token_exists
        self.clean_session = clean_session

    def run(self):
        if self.clean_session:
            try:
                auth_dir = getattr(self.p_client, "auth_storage_dir", None)
                if auth_dir and auth_dir.exists():
                    shutil.rmtree(auth_dir.resolve())
            except Exception as e:
                self.finished_signal.emit(
                    False, f"Failed to clear existing token file: {str(e)}"
                )
                return

        if self.token_exists and not self.clean_session:
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
        self.resize(500, 400)

        self.main_layout = QVBoxLayout(self)

        # --- Options Area (Dialog box with options appears) ---
        self.options_group = QGroupBox("Authentication Options", self)
        self.options_layout = QVBoxLayout(self.options_group)

        self.radio_group = QButtonGroup(self)

        self.radio_existing = QRadioButton("Use an existing token", self)
        self.radio_fresh = QRadioButton(
            "Create a new token (Fresh login - no history)", self
        )

        self.radio_group.addButton(self.radio_existing)
        self.radio_group.addButton(self.radio_fresh)

        self.options_layout.addWidget(self.radio_existing)
        self.options_layout.addWidget(self.radio_fresh)
        self.main_layout.addWidget(self.options_group)

        # --- Logging Area Group ---
        self.logging_group = QGroupBox("Logging Area", self)
        self.logging_layout = QVBoxLayout(self.logging_group)

        self.log_box = QTextEdit(self)
        self.log_box.setReadOnly(True)
        self.logging_layout.addWidget(self.log_box)
        self.main_layout.addWidget(self.logging_group)

        # --- Form Actions ---
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("Proceed")
        self.cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.main_layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.handle_proceed)
        self.button_box.rejected.connect(self.reject)

        self.p_client = None
        self.worker = None
        self.workflow_started = False

    def showEvent(self, event):
        super().showEvent(event)
        if self.p_client is None:
            self.p_client = PlanetClient.getInstance()

        self.evaluate_initial_state()

    def evaluate_initial_state(self):
        """Checks internal state to configure option defaults."""
        self.p_client.get_auth_context()
        has_valid_token = self.p_client.auth_is_valid()

        if has_valid_token:
            self.radio_existing.setChecked(True)
            self.log_box.setText("System status: Existing active token discovered.")
        else:
            self.radio_existing.setEnabled(False)
            self.radio_fresh.setChecked(True)
            self.log_box.setText(
                "System status: No active authentication configuration detected."
            )

    def handle_proceed(self):
        """Triggered when the user confirms their chosen option."""
        if self.workflow_started:
            return

        self.workflow_started = True
        self.options_group.setEnabled(False)
        self.ok_button.setEnabled(False)

        if self.radio_existing.isChecked():
            self.setup_client_with_token()
        else:
            self.setup_client_device_user_workflow()

    def setup_client_with_token(self):
        try:
            self.log_box.setText("--- Planet Authentication Complete ---\n")
            self.log_box.append("User already logged in!\n")
            QCoreApplication.processEvents()

            self.worker = LoginWorker(
                self.p_client, token_exists=True, clean_session=False
            )
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
            self.log_box.setText("--- Planet Authentication Required ---\n")
            self.log_box.append("[Info] Purging local token histories if present...\n")

            auth = self.p_client.auth
            login_info = auth.device_user_login_initiate()

            user_code = login_info.get("user_code", "ERROR")
            url = login_info.get("verification_uri_complete") or login_info.get(
                "verification_uri"
            )

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
