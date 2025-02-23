# Import basic libs
import json

# Import PyQt libs
from qgis.PyQt.QtCore import QObject, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from gbif_extractor.__about__ import __plugin_name__, __version__


class MaxObs(QObject):
    finished_dl = pyqtSignal()
    """Get multiples informations from a getcapabilities request.
    List all layers available, get the maximal extent of all the Wfs' data."""

    def __init__(
        self,
        network_manager=None,
        extent=None,
        url=None,
    ):
        super().__init__()
        self.network_manager = network_manager
        self.extent = extent
        self.url = url

        self._pending_downloads = 0
        self.nb_obs = 0

        self.download()

    @property
    def pending_downloads(self):
        return self._pending_downloads

    def download(self):
        url = "{url}?advanced=false&geometry={polygon}&limit={limit}".format(
            url=self.url,
            polygon=self.extent.asWktPolygon(),
            limit=1,
        )
        url = QUrl(url)
        request = QNetworkRequest(url)
        request.setRawHeader(
            b"User-Agent", bytes(__plugin_name__ + "/" + __version__, encoding="utf-8")
        )
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        reply = self.network_manager.get(request)
        reply.finished.connect(lambda: self.handle_finished(reply))
        self._pending_downloads += 1

    def handle_finished(self, reply):
        self._pending_downloads -= 1
        if reply.error() != QNetworkReply.NoError:
            print(f"code: {reply.error()} message: {reply.errorString()}")
            if reply.error() == 403:
                print("Service down")
        else:
            data_request = reply.readAll().data().decode()
            if self.pending_downloads == 0:
                res = json.loads(data_request)
                self.nb_obs = res["count"]
                self.finished_dl.emit()
