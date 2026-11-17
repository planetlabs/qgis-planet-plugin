# -*- coding: utf-8 -*-
import asyncio
import shutil

import sentry_sdk
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

from ..pe_analytics import USER_LOGIN, analytics_track, is_sentry_dsn_valid
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
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def _emit_finished(self, success, message):
        if self._stop_requested:
            return  # dialog may already be gone; don't touch it
        self.finished_signal.emit(success, message)

    def setup_analytics(self):
        """
        Setup sentry and analytics tracking

        Note: This is done here instead of in
        the planet client to avoid circular imports
        hence tracking is only available in running
        QGIS GUI session.
        """

        if is_sentry_dsn_valid():
            with sentry_sdk.configure_scope() as scope:
                user_email = self.p_client.user()["email"]
                scope.user = {"email": user_email}
        analytics_track(USER_LOGIN)

    def _clear_session_if_needed(self) -> str | None:
        if not self.clean_session:
            return None
        try:
            auth_dir = getattr(self.p_client, "auth_storage_dir", None)
            if auth_dir and auth_dir.exists():
                shutil.rmtree(auth_dir.resolve())
            return None
        except Exception as e:
            return f"Failed to clear existing token file: {str(e)}"

    def _perform_login(self):
        """Attempts log in using existing token or credentials."""
        use_existing_token = self.token_exists and not self.clean_session
        login_arg = None if use_existing_token else self.login_info

        try:
            self.p_client.complete_log_in(login_arg)
            self.setup_analytics()
            self._emit_finished(True, "Success")
        except Exception as e:
            msg = (
                f"Token exists but failed to initialize client! {str(e)}"
                if use_existing_token
                else str(e)
            )
            self._emit_finished(False, msg)

    def run(self):
        if self._stop_requested:
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if error := self._clear_session_if_needed():
                self._emit_finished(False, error)
                return

            if self._stop_requested:
                return

            self._perform_login()
        finally:
            loop.close()


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
        self.cancel_button.setEnabled(False)

        if self.radio_existing.isChecked():
            self.setup_client_with_token()
        else:
            self.setup_client_device_user_workflow()

    def _handle_pre_worker_failure(self, message):
        # Mirrors handle_login_finished's failure branch, for failures that
        # happen before a LoginWorker is even started/running.
        self.log_box.setText(f"Login failed:\n{message}")
        self.ok_button.setEnabled(True)
        self.ok_button.setText("Close")
        self.cancel_button.setEnabled(True)
        self.button_box.accepted.disconnect(self.handle_proceed)
        self.button_box.accepted.connect(self.reject)

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
            self._handle_pre_worker_failure(str(e))

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
            self._handle_pre_worker_failure(str(e))

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
            self.cancel_button.setEnabled(True)
            self.button_box.accepted.disconnect(self.handle_proceed)
            self.button_box.accepted.connect(self.reject)

    def closeEvent(self, event):
        # Ask the background thread to stop cooperatively and wait for it to
        # actually finish, rather than terminating it (which could corrupt
        # the token file if killed mid-write or mid-network-call).
        if self.worker and self.worker.isRunning():
            try:
                self.worker.finished_signal.disconnect(self.handle_login_finished)
            except TypeError:
                pass
            self.worker.request_stop()
            self.worker.wait()
        super().closeEvent(event)
