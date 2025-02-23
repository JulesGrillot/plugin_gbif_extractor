from qgis.PyQt.QtCore import QObject, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import QMessageBox

# project
from gbif_extractor.__about__ import __uri_tracker__


class InternetChecker(QObject):
    """Constructor.

    Class wich is going to ping a website
    to know if the user is connected to internet.
    """

    finished = pyqtSignal()

    def __init__(self, parent=None, manager=None):
        super().__init__(parent)
        self._manager = manager

    @property
    def manager(self):
        return self._manager

    @property
    def pending_ping(self):
        return self._pending_ping

    def ping(self, url):
        qrequest = QNetworkRequest(QUrl(url))
        reply = self.manager.get(qrequest)
        reply.finished.connect(lambda: self.handle_finished(reply))

    def handle_finished(self, reply):
        if reply.error() != QNetworkReply.NoError:
            # If the user does not have an internet connexion,
            # the plugin does not launch.
            msg = QMessageBox()
            if reply.error() == 403:
                msg.critical(
                    None,
                    self.tr("Error"),
                    self.tr("Github is down."),
                )
            elif reply.error() == 3:
                msg.critical(
                    None,
                    self.tr("Error"),
                    self.tr("You are not connected to the Internet."),
                )
            else:
                msg.critical(
                    None,
                    self.tr("Error"),
                    self.tr(
                        "Code error : {code}\nGo to\n{tracker}\nto report the issue.".format(
                            code=str(reply.error()), tracker=__uri_tracker__
                        )
                    ),
                )
        else:
            self.finished.emit()
