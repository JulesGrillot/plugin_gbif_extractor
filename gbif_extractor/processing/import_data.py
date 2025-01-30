# Import basic libs
import json

# Import PyQt libs
from PyQt5.QtCore import QObject, QUrl, pyqtSignal
from PyQt5.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import NULL, QgsFeature, QgsGeometry, QgsPointXY


class ImportData(QObject):
    finished_dl = pyqtSignal()
    """
    """

    def __init__(
        self,
        network_manager=None,
        project=None,
        layer=None,
        rectangle=None,
        dlg=None,
        url=None,
    ):
        super().__init__()

        self._pending_downloads = 0
        self._pending_pages = 0
        self._pending_count = 0
        self.network_manager = network_manager
        self.project = project
        self.layer = layer
        self.geom = QgsGeometry().fromRect(rectangle)
        self.dlg = dlg
        self.url = url

        self.new_features = []

        # Obs limit by pages, default is 20
        self.limit = 20
        self.max_obs = 0
        self.total_pages = 0

        self.download()

    @property
    def pending_downloads(self):
        return self._pending_downloads

    @property
    def pending_pages(self):
        return self._pending_pages

    @property
    def pending_count(self):
        return self._pending_count

    def download(self):
        url = "{url}?advanced=false&geometry={polygon}&offset={offset}&limit={limit}".format(
            url=self.url,
            offset=self.pending_count,
            polygon=self.geom.asWkt(),
            limit=self.limit,
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
                if self.pending_pages == 0:
                    self.max_obs = res["count"]
                    self.total_pages = int(self.max_obs / self.limit) + 1
                    self.dlg.thread.set_max(self.total_pages)
                    self.dlg.thread.add_one(self.pending_pages)
                    self.dlg.select_progress_bar_label.setText(
                        self.tr("Downloaded data : " + str(0) + "/" + str(self.max_obs))
                    )
                for obs in res["results"]:
                    new_geom = QgsGeometry.fromPointXY(
                        QgsPointXY(obs["decimalLongitude"], obs["decimalLatitude"])
                    )
                    new_feature = QgsFeature(self.layer.fields())
                    new_feature.setGeometry(new_geom)
                    field_index = 0
                    new_feature.setAttribute(field_index, str(obs["key"]))
                    field_index += 1
                    new_feature.setAttribute(field_index, str(obs["occurrenceStatus"]))
                    field_index += 1
                    new_feature.setAttribute(field_index, obs["taxonRank"])
                    field_index += 1
                    if "kingdom" in list(obs.keys()):
                        new_feature.setAttribute(field_index, obs["kingdom"])
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    if "phylum" in list(obs.keys()):
                        new_feature.setAttribute(field_index, obs["phylum"])
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    if "class" in list(obs.keys()):
                        new_feature.setAttribute(field_index, obs["class"])
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    if "order" in list(obs.keys()):
                        new_feature.setAttribute(field_index, obs["order"])
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    if "family" in list(obs.keys()):
                        new_feature.setAttribute(field_index, obs["family"])
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    if "genus" in list(obs.keys()):
                        new_feature.setAttribute(field_index, obs["genus"])
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    if "species" in list(obs.keys()):
                        new_feature.setAttribute(field_index, obs["species"])
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    new_feature.setAttribute(field_index, str(obs["acceptedTaxonKey"]))
                    field_index += 1
                    if "taxonID" in list(obs.keys()):
                        new_feature.setAttribute(field_index, str(obs["taxonID"]))
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    if "acceptedScientificName" in list(obs.keys()):
                        new_feature.setAttribute(
                            field_index, obs["acceptedScientificName"]
                        )
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    if "recordedBy" in list(obs.keys()):
                        new_feature.setAttribute(field_index, str(obs["recordedBy"]))
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    if "identifiedBy" in list(obs.keys()):
                        new_feature.setAttribute(field_index, str(obs["identifiedBy"]))
                    else:
                        new_feature.setAttribute(
                            field_index,
                            str(
                                [
                                    d["identifier"]
                                    for d in obs["identifiers"]
                                    if "identifier" in d
                                ]
                            ),
                        )
                    field_index += 1
                    if "eventDate" in list(obs.keys()):
                        new_feature.setAttribute(field_index, str(obs["eventDate"]))
                    elif "verbatimEventDate" in list(obs.keys()):
                        new_feature.setAttribute(
                            field_index, str(obs["verbatimEventDate"])
                        )
                    else:
                        new_feature.setAttribute(field_index, "")
                    field_index += 1
                    new_feature.setAttribute(
                        field_index, obs["_publishingOrgKey"]["title"]
                    )
                    field_index += 1
                    new_feature.setAttribute(field_index, obs["_datasetKey"]["title"])
                    field_index += 1
                    if "informationWithheld" in list(obs.keys()):
                        new_feature.setAttribute(
                            field_index, str(obs["informationWithheld"])
                        )
                    else:
                        new_feature.setAttribute(field_index, NULL)
                    field_index += 1
                    new_feature.setAttribute(
                        field_index,
                        "https://www.gbif.org/fr/occurrence/" + str(obs["key"]),
                    )
                    field_index += 1
                    self.new_features.append(new_feature)

                if self.pending_pages < self.total_pages:
                    self.dlg.thread.add_one(self.pending_pages)
                    self.dlg.select_progress_bar_label.setText(
                        self.tr(
                            "Downloaded data : "
                            + str(self.pending_count)
                            + "/"
                            + str(self.max_obs)
                        )
                    )
                    self._pending_pages += 1
                    self._pending_count += self.limit
                    self.download()
                else:
                    # Add the new feature to the temporary layer
                    self.layer.startEditing()
                    self.layer.dataProvider().addFeatures(self.new_features)
                    self.layer.updateExtents()
                    self.layer.commitChanges()
                    self.layer.triggerRepaint()

                    self.finished_dl.emit()
