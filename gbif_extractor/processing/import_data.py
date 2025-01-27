# Import basic libs
import json

# Import PyQt libs
from PyQt5.QtCore import QObject, QUrl, pyqtSignal
from PyQt5.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY


class ImportData(QObject):
    finished_dl = pyqtSignal()
    """Get multiples informations from a getcapabilities request.
    List all layers available, get the maximal extent of all the Wfs' data."""

    def __init__(
        self,
        network_manager=None,
        project=None,
        layer=None,
        rectangle=None,
        dlg=None
    ):
        super().__init__()

        self._pending_downloads = 0
        self._pending_pages = 1
        self.network_manager = network_manager
        self.project = project
        self.layer = layer
        self.geom = QgsGeometry().fromRect(rectangle)
        self.dlg = dlg

        self.new_features = []

        self.max_obs = 0
        self.total_pages = 0

        self.download()

    @property
    def pending_downloads(self):
        return self._pending_downloads

    @property
    def pending_pages(self):
        return self._pending_pages

    def download(self):
        url = "https://www.gbif.org/api/occurrence/search?advanced=false&geometry={polygon}&offset={offset}".format(
            offset=self.pending_pages, polygon=self.geom.asWkt()
        )
        url = QUrl(url)
        request = QNetworkRequest(url)
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
                if self.pending_pages == 1:
                    self.max_obs = res["count"]
                    self.total_pages = int(self.max_obs / 20) + 1
                    self.dlg.thread.set_max(self.total_pages)
                    self.dlg.thread.add_one(self.pending_pages)
                    self.dlg.select_progress_bar_label.setText(
                        self.tr("Downloaded data : " + str(1) + "/" + str(self.total_pages))
                    )
                for obs in res["results"]:
                    new_geom = QgsGeometry.fromPointXY(
                        QgsPointXY(obs["decimalLongitude"], obs["decimalLatitude"])
                    )
                    new_feature = QgsFeature(self.layer.fields())
                    new_feature.setGeometry(new_geom)
                    new_feature.setAttribute(0, str(obs["key"]))
                    new_feature.setAttribute(1, obs["taxonRank"])
                    new_feature.setAttribute(2, obs["kingdom"])
                    new_feature.setAttribute(3, obs["phylum"])
                    new_feature.setAttribute(4, obs["order"])
                    new_feature.setAttribute(5, obs["family"])
                    new_feature.setAttribute(6, obs["genus"])
                    new_feature.setAttribute(7, obs["species"])
                    new_feature.setAttribute(8, str(obs["acceptedTaxonKey"]))
                    if "taxonID" in list(obs.keys()):
                        new_feature.setAttribute(9, str(obs["taxonID"]))
                    else:
                        new_feature.setAttribute(9, "")
                    if obs["taxonRank"] == "SUBSPECIES":
                        print(obs)
                    if "acceptedScientificName" in list(obs.keys()):
                        new_feature.setAttribute(10, obs["acceptedScientificName"])
                    else:
                        new_feature.setAttribute(10, "")
                    if "recordedBy" in list(obs.keys()):
                        new_feature.setAttribute(11, str(obs["recordedBy"]))
                    else:
                        new_feature.setAttribute(11, "")
                    
                    if "identifiedBy" in list(obs.keys()):
                        new_feature.setAttribute(12, str(obs["identifiedBy"]))
                    else:
                        new_feature.setAttribute(
                            12, str([d["identifier"] for d in obs["identifiers"] if "identifier" in d])
                        )

                    new_feature.setAttribute(13, str(obs["eventDate"]))
                    new_feature.setAttribute(14, obs["_publishingOrgKey"]["title"])
                    new_feature.setAttribute(15, obs["_datasetKey"]["title"])
                    new_feature.setAttribute(16, 1)
                    new_feature.setAttribute(
                        17, "https://www.gbif.org/fr/occurrence/" + str(obs["key"])
                    )
                    self.new_features.append(new_feature)

                if self.pending_pages < self.total_pages:
                    self.dlg.thread.add_one(self.pending_pages)
                    self.dlg.select_progress_bar_label.setText(
                        self.tr("Downloaded data : " + str(self.pending_pages) + "/" + str(self.total_pages))
                    )
                    self._pending_pages += 20
                    self.download()
                else:
                    # Add the new feature to the temporary layer
                    self.layer.startEditing()
                    self.layer.dataProvider().addFeatures(self.new_features)
                    self.layer.updateExtents()
                    self.layer.commitChanges()
                    self.layer.triggerRepaint()

                    self.finished_dl.emit()
