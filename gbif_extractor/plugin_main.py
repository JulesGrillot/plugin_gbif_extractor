#! python3  # noqa: E265

"""
    Main plugin module.
"""

import datetime
import os.path

# standard
from functools import partial
from pathlib import Path

from PyQt5.QtCore import QObject, QVariant, pyqtSignal
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

# PyQGIS
from qgis.core import QgsApplication, QgsField, QgsProject, QgsSettings, QgsVectorLayer
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

# project
from gbif_extractor.__about__ import (
    DIR_PLUGIN_ROOT,
    __icon_path__,
    __title__,
    __uri_homepage__,
    __uri_tracker__,
    __wfs_name__,
    __wfs_uri__,
)
from gbif_extractor.gui.dlg_main import GbifExtractorDialog
from gbif_extractor.gui.dlg_settings import PlgOptionsFactory
from gbif_extractor.processing import GbifExtractorProvider, ImportData
from gbif_extractor.toolbelt import PlgLogger

# ############################################################################
# ########## Classes ###############
# ##################################


class GbifExtractorPlugin:
    def __init__(self, iface: QgisInterface):
        """Constructor.

        :param iface: An interface instance \
            that will be passed to this class which \
        provides the hook by which you can manipulate \
            the QGIS application at run time.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.project = QgsProject.instance()
        self.manager = QNetworkAccessManager()
        self.log = PlgLogger().log
        self.provider = None
        self.pluginIsActive = False
        self.url = __wfs_uri__
        self.action_launch = None

        # translation
        # initialize the locale
        self.locale: str = QgsSettings().value("locale/userLocale", QLocale().name())[
            0:2
        ]
        locale_path: Path = (
            DIR_PLUGIN_ROOT / f"resources/i18n/{__title__.lower()}_{self.locale}.qm"
        )
        self.log(message=f"Translation: {self.locale}, {locale_path}", log_level=4)
        if locale_path.exists():
            self.translator = QTranslator()
            self.translator.load(str(locale_path.resolve()))
            QCoreApplication.installTranslator(self.translator)

    def initGui(self):
        """Set up plugin UI elements."""

        # settings page within the QGIS preferences menu
        self.options_factory = PlgOptionsFactory()
        self.iface.registerOptionsWidgetFactory(self.options_factory)

        # -- Actions
        self.action_launch = QAction(
            QIcon(str(__icon_path__)),
            self.tr("{} Extractor".format(__wfs_name__)),
            self.iface.mainWindow(),
        )
        self.iface.addToolBarIcon(self.action_launch)
        self.action_launch.triggered.connect(lambda: self.run())
        self.action_help = QAction(
            QgsApplication.getThemeIcon("mActionHelpContents.svg"),
            self.tr("Help"),
            self.iface.mainWindow(),
        )
        self.action_help.triggered.connect(
            partial(QDesktopServices.openUrl, QUrl(__uri_homepage__))
        )

        self.action_settings = QAction(
            QgsApplication.getThemeIcon("console/iconSettingsConsole.svg"),
            self.tr("Settings"),
            self.iface.mainWindow(),
        )
        self.action_settings.triggered.connect(
            lambda: self.iface.showOptionsDialog(
                currentPage="mOptionsPage{}".format(__title__)
            )
        )

        # -- Menu
        self.iface.addPluginToMenu(
            "{} Extractor".format(__wfs_name__), self.action_launch
        )
        self.iface.addPluginToMenu(
            "{} Extractor".format(__wfs_name__), self.action_settings
        )
        self.iface.addPluginToMenu(
            "{} Extractor".format(__wfs_name__), self.action_help
        )

        # -- Processing
        self.initProcessing()

        # -- Help menu

        # documentation
        self.iface.pluginHelpMenu().addSeparator()
        self.action_help_plugin_menu_documentation = QAction(
            QIcon(str(__icon_path__)),
            f"{__wfs_name__} Extractor - Documentation",
            self.iface.mainWindow(),
        )
        self.action_help_plugin_menu_documentation.triggered.connect(
            partial(QDesktopServices.openUrl, QUrl(__uri_homepage__))
        )

        self.iface.pluginHelpMenu().addAction(
            self.action_help_plugin_menu_documentation
        )

    def initProcessing(self):
        self.provider = GbifExtractorProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def tr(self, message: str) -> str:
        """Get the translation for a string using Qt translation API.

        :param message: string to be translated.
        :type message: str

        :returns: Translated version of message.
        :rtype: str
        """
        return QCoreApplication.translate(self.__class__.__name__, message)

    def unload(self):
        """Cleans up when plugin is disabled/uninstalled."""
        # -- Clean up menu
        self.iface.removePluginMenu(
            "{} Extractor".format(__wfs_name__), self.action_launch
        )
        self.iface.removeToolBarIcon(self.action_launch)
        self.iface.removePluginMenu(
            "{} Extractor".format(__wfs_name__), self.action_help
        )
        self.iface.removePluginMenu(
            "{} Extractor".format(__wfs_name__), self.action_settings
        )

        # -- Clean up preferences panel in QGIS settings
        self.iface.unregisterOptionsWidgetFactory(self.options_factory)

        # -- Unregister processing
        QgsApplication.processingRegistry().removeProvider(self.provider)

        # remove from QGIS help/extensions menu
        if self.action_help_plugin_menu_documentation:
            self.iface.pluginHelpMenu().removeAction(
                self.action_help_plugin_menu_documentation
            )

        # remove actions
        del self.action_launch
        del self.action_settings
        del self.action_help
        self.pluginIsActive = False

    def run(self):
        """Main process.

        Try to connect to internet, if successfull, the dialog appear.
        Else an error message appear.
        """
        self.internet_checker = InternetChecker(None, self.manager)
        self.internet_checker.finished.connect(self.handle_finished)
        self.internet_checker.ping("https://github.com/")

    def handle_finished(self):
        # Check if plugin is already launched
        if not self.pluginIsActive:
            self.pluginIsActive = True
            # Open Dialog
            self.dlg = GbifExtractorDialog(
                self.project, self.iface, self.url, self.manager
            )
            self.dlg.show()
            # If there is no layers, an OSM layer is added
            # to simplify the rectangle drawing
            if len(self.project.instance().mapLayers()) == 0:

                # Type of WMTS, url and name
                type = "xyz"
                url = "http://tile.openstreetmap.org/{z}/{x}/{y}.png"
                name = "OpenStreetMap"
                uri = "type=" + type + "&url=" + url

                # Add WMTS to the QgsProject
                self.iface.addRasterLayer(uri, name, "wms")
            result = self.dlg.exec_()
            if result:
                # If dialog is accepted, "OK" is pressed, the process is launch
                self.processing()
            else:
                # Else the dialog close and plugin can be launched again
                self.pluginIsActive = False
        # If the plugin is already launched, clicking on the plugin icon will
        # put back the window on top
        else:
            self.dlg.activateWindow()

    def processing(self):
        """Processing chain if the dialog is accepted
        Depending on user's choices, a folder can be created, the wfs is
        requested and the layers in the specific extent can be added to
        the QGIS project

        """
        # Show the dialog back for the ProgressBar
        self.dlg.show()

        # Creation of the folder name
        today = datetime.datetime.now()
        year = today.year
        month = today.strftime("%m")
        day = today.strftime("%d")
        hour = today.strftime("%H")
        minute = today.strftime("%M")
        folder = (
            "GbifExport_"
            + str(year)
            + str(month)
            + str(day)
            + "_"
            + str(hour)
            + str(minute)
        )
        if self.dlg.save_result_checkbox.isChecked():
            # Creation of the folder
            path = self.dlg.line_edit_output_folder.text() + "/" + str(folder)
            if not os.path.exists(path):
                os.makedirs(path)
        else:
            path = None

        # Creation of a group of layers to store the results of the request
        if self.dlg.add_to_project_checkbox.isChecked():
            self.project.instance().layerTreeRoot().insertGroup(0, folder)
            self.group = self.project.instance().layerTreeRoot().findGroup(folder)
        # Fetch if the results must be clipped or kept full
        for button in self.dlg.geom_button_group.buttons():
            if button.isChecked():
                result_geometry = button.accessibleName()

        geom_type = "Point"
        self.new_layer = QgsVectorLayer(geom_type + "?crs=epsg:4326", "GBIF", "memory")
        self.new_layer.startEditing()
        self.new_layer.addAttribute(QgsField("id", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("niveau", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("regne", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("phylum", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("ordre", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("famille", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("genre", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("espece", QVariant.String, "string", 254))
        self.new_layer.addAttribute(
            QgsField("id_tax_gbif", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(
            QgsField("id_tax_local", QVariant.String, "string", 254)
        )
        
        self.new_layer.addAttribute(
            QgsField("nom_scien", QVariant.String, "string", 100000)
        )
        self.new_layer.addAttribute(
            QgsField("observat", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(
            QgsField("identifi", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(QgsField("date", QVariant.String, "string", 254))
        self.new_layer.addAttribute(
            QgsField("organisme", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(QgsField("projet", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("effectif", QVariant.Int, "integer", 10))
        self.new_layer.addAttribute(QgsField("url", QVariant.String, "string", 254))
        self.new_layer.commitChanges()
        self.new_layer.triggerRepaint()

        import_data = ImportData(
            self.manager, self.project, self.new_layer, self.dlg.extent, self.dlg
        )
        import_data.finished_dl.connect(self.finished_import)

    def finished_import(self):
        # If a layer is created and needs to be added to the project
        if (
            self.new_layer.featureCount() > 0
            and self.dlg.add_to_project_checkbox.isChecked()
        ):
            # If output format is a SHP or a GEOJSON or if the
            # layers are not saved. Saved GPKG are processed
            # differently.
            if (
                self.dlg.output_format() != "gpkg"
                or self.dlg.output_format() == "gpkg"
                and not self.dlg.save_result_checkbox.isChecked()
            ):
                self.project.instance().addMapLayer(self.new_layer, False)
                self.group.addLayer(self.new_layer)

        # Increase the ProgressBar value
        # n = n + 1
        # self.dlg.thread.add_one()
        # self.dlg.select_progress_bar_label.setText(
        #     self.tr("Downloaded data : " + str(n) + "/" + str(max))
        # )

        # If the user wants to saved as GPKG
        if (
            self.dlg.output_format() == "gpkg"
            and self.dlg.save_result_checkbox.isChecked()
        ):
            # If a layer as been saved, the GPKG is opened and every layer are
            # added to the project
            # if (len(good_list) / n) > 0:
            if self.new_layer.featureCount() > 0:
                gpkg = QgsVectorLayer(self.new_layer, "", "ogr")
                layers = gpkg.dataProvider().subLayers()
                for layer in layers:
                    name = layer.split("!!::!!")[1]
                    uri = "%s|layername=%s" % (
                        self.new_layer,
                        name,
                    )
                    # Create layer
                    final_layer = QgsVectorLayer(uri, name, "ogr")
                    self.project.instance().addMapLayer(final_layer, False)
                    self.group.addLayer(final_layer)
        # Once it's finished, the ProgressBar is set back to 0
        self.dlg.thread.finish()
        self.dlg.select_progress_bar_label.setText("")
        self.dlg.thread.reset_value()
        self.dlg.close()
        self.pluginIsActive = False


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
                    self.tr("GBIF Services' are down."),
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
