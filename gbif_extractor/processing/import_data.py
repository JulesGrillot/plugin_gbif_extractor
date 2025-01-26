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
    ):
        super().__init__()

        self._pending_downloads = 0
        self._pending_pages = 1
        self.network_manager = network_manager
        self.project = project
        self.layer = layer
        self.geom = QgsGeometry().fromRect(rectangle)

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
            print(data_request)
            if self.pending_downloads == 0:
                res = json.loads(data_request)
                self.max_obs = res["count"]
                self.total_pages = int(self.max_obs / 20) + 1
                for obs in res["results"]:
                    print(list(obs.keys()))
                    new_geom = QgsGeometry.fromPointXY(
                        QgsPointXY(obs["decimalLongitude"], obs["decimalLatitude"])
                    )
                    new_feature = QgsFeature(self.layer.fields())
                    new_feature.setGeometry(new_geom)
                    new_feature.setAttribute(0, str(obs["key"]))
                    new_feature.setAttribute(1, str(obs["acceptedTaxonKey"]))
                    if "taxonID" in list(obs.keys()):
                        new_feature.setAttribute(2, str(obs["taxonID"]))
                    else:
                        new_feature.setAttribute(2, "")
                    new_feature.setAttribute(3, obs["taxonRank"])
                    if obs["taxonRank"].lower() in [
                        "kingdom",
                        "phylum",
                        "order",
                        "family",
                        "genus",
                        "species",
                    ]:
                        new_feature.setAttribute(4, obs[obs["taxonRank"].lower()])

                    else:
                        new_feature.setAttribute(5, obs["acceptedScientificName"])
                    if "originalNameUsage" in list(obs.keys()):
                        new_feature.setAttribute(6, str(obs["originalNameUsage"]))
                    else:
                        new_feature.setAttribute(6, "")
                    new_feature.setAttribute(7, str(obs["recordedBy"]))
                    if "identifiedBy" in list(obs.keys()):
                        new_feature.setAttribute(8, str(obs["identifiedBy"]))
                    else:
                        new_feature.setAttribute(
                            8, str(list(obs["identifiers"].values()))
                        )

                    new_feature.setAttribute(8, str(obs["eventDate"]))
                    new_feature.setAttribute(9, obs["_publishingOrgKey"]["title"])
                    new_feature.setAttribute(10, obs["_datasetKey"]["title"])
                    new_feature.setAttribute(11, 1)
                    new_feature.setAttribute(
                        12, "https://www.gbif.org/fr/occurrence/" + str(obs["key"])
                    )
                    self.new_features.append(new_feature)

                if self.pending_pages < self.total_pages:
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
