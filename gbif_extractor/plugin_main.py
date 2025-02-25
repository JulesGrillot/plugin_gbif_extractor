#! python3  # noqa: E265

"""
    Main plugin module.
"""

import datetime
import os.path

# standard
from functools import partial
from pathlib import Path

# PyQGIS
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsField,
    QgsProject,
    QgsSettings,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator, QUrl, QVariant
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtNetwork import QNetworkAccessManager
from qgis.PyQt.QtWidgets import QAction, QMessageBox

# project
from gbif_extractor.__about__ import (
    DIR_PLUGIN_ROOT,
    __icon_path__,
    __layer_name__,
    __layer_source_name__,
    __plugin_name__,
    __service_uri__,
    __title__,
    __uri_homepage__,
)
from gbif_extractor.gui.dlg_main import GbifExtractorDialog
from gbif_extractor.gui.dlg_settings import PlgOptionsFactory
from gbif_extractor.processing import GbifExtractorProvider, ImportData
from gbif_extractor.toolbelt import InternetChecker, PlgLogger

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
        self.url = __service_uri__
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
            self.tr("{}".format(__plugin_name__)),
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
        self.iface.addPluginToMenu("{}".format(__plugin_name__), self.action_launch)
        self.iface.addPluginToMenu("{}".format(__plugin_name__), self.action_settings)
        self.iface.addPluginToMenu("{}".format(__plugin_name__), self.action_help)

        # -- Processing
        self.initProcessing()

        # -- Help menu

        # documentation
        self.iface.pluginHelpMenu().addSeparator()
        self.action_help_plugin_menu_documentation = QAction(
            QIcon(str(__icon_path__)),
            f"{__plugin_name__} - Documentation",
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
        self.iface.removePluginMenu("{}".format(__plugin_name__), self.action_launch)
        self.iface.removeToolBarIcon(self.action_launch)
        self.iface.removePluginMenu("{}".format(__plugin_name__), self.action_help)
        self.iface.removePluginMenu("{}".format(__plugin_name__), self.action_settings)

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
                self.project, self.iface, self.manager, self.url
            )
            self.dlg.activate_window()
            # If there is no layers, an OSM layer is added
            # to simplify the rectangle drawing
            if len(self.project.instance().mapLayers()) == 0:

                # Type of WMTS, url and name
                wms_type = "xyz"
                url = "http://tile.openstreetmap.org/{z}/{x}/{y}.png"
                name = "OpenStreetMap"
                uri = "type=" + wms_type + "&url=" + url

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
            self.dlg.activate_window()

    def processing(self):
        """Processing chain if the dialog is accepted
        Depending on user's choices, a folder can be created, the service is
        requested and the layers in the specific extent can be added to
        the QGIS project

        """
        self.start_data_import(self.dlg.nb_obs)
        self.dlg.show()

    def start_data_import(self, nb_obs):
        if nb_obs > 0:
            # Creation of the folder name
            today = datetime.datetime.now()
            year = today.year
            month = today.strftime("%m")
            day = today.strftime("%d")
            hour = today.strftime("%H")
            minute = today.strftime("%M")
            folder = (
                str(__layer_name__)
                + "_"
                + str(year)
                + str(month)
                + str(day)
                + "_"
                + str(hour)
                + str(minute)
            )
            if self.dlg.save_result_checkbox.isChecked():
                # Creation of the folder
                self.path = self.dlg.line_edit_output_folder.text() + "/" + str(folder)
                if not os.path.exists(self.path):
                    os.makedirs(self.path)
            else:
                self.path = None

            # Creation of a group of layers to store the results of the request
            if self.dlg.add_to_project_checkbox.isChecked():
                self.project.instance().layerTreeRoot().insertGroup(0, folder)
                self.group = self.project.instance().layerTreeRoot().findGroup(folder)

            geom_type = "Point"
            self.new_layer = QgsVectorLayer(
                geom_type + "?crs=" + self.dlg.crs_selector.crs().authid(),
                str(__layer_name__),
                "memory",
            )
            self.add_field()

            self.import_data = ImportData(
                self.manager,
                self.project,
                self.new_layer,
                self.dlg.extent,
                self.dlg,
                self.url,
            )
            self.import_data.download(nb_obs)
            self.import_data.finished_dl.connect(self.finished_import)
        else:
            # If there is no observation in the extent.
            msg = QMessageBox()
            msg.critical(
                None,
                self.tr("Error"),
                self.tr("No Observation in the selected extent."),
            )
            self.dlg.close()
            self.pluginIsActive = False
            self.handle_finished()

    def finished_import(self):
        # If a layer is created and needs to be added to the project
        if self.new_layer.featureCount() > 0:
            # If the user wants to saved as GPKG
            if self.dlg.save_result_checkbox.isChecked():
                context = self.project.instance().transformContext()
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.layerName = str(__layer_name__)
                options.fileEncoding = self.new_layer.dataProvider().encoding()
                if self.dlg.selected_output_format() == "gpkg":
                    # If a layer as been saved, the GPKG is opened and every layer are
                    # added to the project
                    # Specific procedure if the layer must be saved as a GPKG.
                    options.driverName = "GPKG"
                    # Check if the GeoPackage already exists,
                    # to know if it's need to be created or not
                    if os.path.isfile(
                        self.path + "/" + str(__layer_source_name__) + ".gpkg"
                    ):
                        options.actionOnExistingFile = (
                            QgsVectorFileWriter.CreateOrOverwriteLayer
                        )

                    if Qgis.QGIS_VERSION_INT > 32000:
                        QgsVectorFileWriter.writeAsVectorFormatV3(
                            self.new_layer,
                            self.path + "/" + str(__layer_source_name__) + ".gpkg",
                            context,
                            options,
                        )
                    else:
                        QgsVectorFileWriter.writeAsVectorFormatV2(
                            self.new_layer,
                            self.path + "/" + str(__layer_source_name__) + ".gpkg",
                            context,
                            options,
                        )
                    final_layer = self.path + "/" + str(__layer_source_name__) + ".gpkg"
                    gpkg = QgsVectorLayer(
                        final_layer,
                        "",
                        "ogr",
                    )
                    layers = gpkg.dataProvider().subLayers()
                    for layer in layers:
                        name = layer.split("!!::!!")[1]
                        uri = "%s|layername=%s" % (
                            final_layer,
                            name,
                        )
                        # Create layer
                        self.new_layer = QgsVectorLayer(uri, name, "ogr")
                else:
                    output = (
                        self.path
                        + "/"
                        + str(__layer_source_name__)
                        + "."
                        + self.dlg.selected_output_format()
                    )
                    # For every other format, the procedure is the same.
                    if self.dlg.selected_output_format() == "shp":
                        options.driverName = "ESRI Shapefile"
                    elif self.dlg.selected_output_format() == "geojson":
                        options.driverName = "GeoJSON"
                    if Qgis.QGIS_VERSION_INT > 32000:
                        QgsVectorFileWriter.writeAsVectorFormatV3(
                            self.new_layer,
                            output,
                            context,
                            options,
                        )
                    else:
                        QgsVectorFileWriter.writeAsVectorFormatV2(
                            self.new_layer,
                            output,
                            context,
                            options,
                        )
                    self.new_layer = QgsVectorLayer(
                        output,
                        str(__layer_name__),
                        "ogr",
                    )
            if self.dlg.add_to_project_checkbox.isChecked():
                # If output format is a SHP or a GEOJSON or if the
                # layers are not saved. Saved GPKG are processed
                # differently.
                self.project.instance().addMapLayer(self.new_layer, False)
                self.group.addLayer(self.new_layer)
        # Once it's finished, the ProgressBar is set back to 0
        self.dlg.thread.finish()
        self.dlg.select_progress_bar_label.setText("")
        self.dlg.thread.reset_value()
        self.dlg.close()
        self.pluginIsActive = False

    def add_field(self):
        self.new_layer.startEditing()
        self.new_layer.addAttribute(QgsField("id", QVariant.String, "string", 254))
        self.new_layer.addAttribute(
            QgsField("occurence_statuts", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(QgsField("rank", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("kingdom", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("phylum", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("class", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("order", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("family", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("genus", QVariant.String, "string", 254))
        self.new_layer.addAttribute(QgsField("species", QVariant.String, "string", 254))
        self.new_layer.addAttribute(
            QgsField("id_tax_gbif", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(
            QgsField("id_tax_local", QVariant.String, "string", 254)
        )

        self.new_layer.addAttribute(QgsField("name", QVariant.String, "string", 100000))
        self.new_layer.addAttribute(
            QgsField("observer", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(
            QgsField("identifier", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(QgsField("date", QVariant.String, "string", 254))
        self.new_layer.addAttribute(
            QgsField("institution", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(QgsField("project", QVariant.String, "string", 254))
        self.new_layer.addAttribute(
            QgsField("precision", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(
            QgsField("information", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(
            QgsField("gbif_url", QVariant.String, "string", 254)
        )
        self.new_layer.addAttribute(
            QgsField("taxon_url", QVariant.String, "string", 254)
        )
        self.new_layer.commitChanges()
        self.new_layer.triggerRepaint()
