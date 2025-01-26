import json

from PyQt5.QtCore import QObject, QUrl, pyqtSignal
from PyQt5.QtNetwork import QNetworkReply, QNetworkRequest


class GetTaxrefRequest(QObject):
    finished_dl = pyqtSignal()
    """Get multiples informations from a getcapabilities request.
    List all layers available, get the maximal extent of all the Wfs' data."""

    def __init__(
        self,
        network_manager=None,
        project=None,
        layer=None,
        field_name=None,
        field_rank=None,
    ):
        super().__init__()
        self.network_manager = network_manager
        self.project = project
        self.layer = layer
        self.field_name = field_name
        self.field_rank = field_rank
        self._pending_downloads = 0

        self.ids = []
        self.names = []
        self.rank = []

        for obs in self.layer.getFeatures():
            self.ids.append(obs.id())
            self.names.append(obs[self.field_name])
            self.rank.append(obs[self.field_rank])
        self._pending_downloads = len(self.names)
        self._iterate_names = 0
        self.download(
            self.ids[self._iterate_names],
            self.names[self._iterate_names],
            self.rank[self._iterate_names],
        )

    @property
    def pending_downloads(self):
        return self._pending_downloads

    @property
    def iterate_names(self):
        return self._iterate_names

    def download(self, feature_id, nom, rank):
        if rank.lower() == "stateofmatter":
            self._iterate_names += 1
            self.download(
                self.ids[self._iterate_names],
                self.names[self._iterate_names],
                self.rank[self._iterate_names],
            )
        else:
            if rank.lower() == "complex" or rank.lower() == "hybrid":
                rank = "species"
            elif rank.lower() == "epifamily" or rank.lower() == "section":
                rank = "genus"
            elif rank.lower() == "subtribe":
                rank = "subfamily"
            url = "https://api.checklistbank.org/nameusage/search?content=SCIENTIFIC_NAME&datasetKey=2008&facet=datasetKey&facet=rank&facet=issue&facet=status&facet=nomStatus&facet=nameType&facet=field&facet=authorship&facet=authorshipYear&facet=extinct&facet=environment&facet=origin&limit=50&offset=0&q={nom}&rank={rank}&type=PREFIX".format(
                nom=nom.split("(")[0], rank=rank.lower()
            )
            request = QNetworkRequest(QUrl(url))
            request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
            reply = self.network_manager.get(request)
            reply.finished.connect(lambda: self.handle_finished(reply, feature_id))
            self._iterate_names += 1

    def handle_finished(self, reply, feature_id):
        self._pending_downloads -= 1
        if reply.error() != QNetworkReply.NoError:
            print(f"code: {reply.error()} message: {reply.errorString()}")
            if reply.error() == 403:
                print("Service down")
        else:
            data_request = reply.readAll().data().decode()
            if data_request != "":
                res = json.loads(data_request)
                if "result" in res:
                    taxref_id = res["result"][0]["id"]
                    taxref_name = res["result"][0]["usage"]["label"]
                    self.layer.startEditing()
                    self.layer.changeAttributeValue(
                        feature_id,
                        self.layer.fields().indexFromName("cd_nom"),
                        taxref_id,
                    )
                    self.layer.changeAttributeValue(
                        feature_id,
                        self.layer.fields().indexFromName("nom_scien"),
                        taxref_name,
                    )
                    self.layer.commitChanges()
                    self.layer.triggerRepaint()
                if self.pending_downloads == 0:
                    self.project.addMapLayer(self.layer)
                    self.finished_dl.emit()
                else:
                    self.download(
                        self.ids[self._iterate_names],
                        self.names[self._iterate_names],
                        self.rank[self._iterate_names],
                    )
