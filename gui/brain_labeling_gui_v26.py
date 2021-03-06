#! /usr/bin/env python

"""
This version supports visualization of contours of multiple levels.
"""

import sys
import os
from datetime import datetime
import time
import json
from collections import defaultdict, OrderedDict

import numpy as np
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import LineString as ShapelyLineString
from shapely.geometry import LinearRing as ShapelyLineRing
from skimage.color import label2rgb
from pandas import DataFrame

sys.path.append(os.environ['REPO_DIR'] + '/utilities')
from utilities2015 import *
from data_manager import DataManager
from metadata import *
from annotation_utilities import *
from gui_utilities import *

from ui.ui_BrainLabelingGui_v15 import Ui_BrainLabelingGui

from widgets.custom_widgets import *
from widgets.SignalEmittingItems import *
from widgets.DrawableZoomableBrowsableGraphicsScene_ForLabeling_v2 import DrawableZoomableBrowsableGraphicsScene_ForLabeling

from DataFeeder import ImageDataFeeder_v2, VolumeResectionDataFeeder

######################################################################

MARKER_COLOR_CHAR = 'w'

#######################################################################

class ReadRGBComponentImagesThread(QThread):
    def __init__(self, stack, sections):
        QThread.__init__(self)
        self.stack = stack
        self.sections = sections

    def __del__(self):
        self.wait()

    def run(self):
        for sec in self.gscenes['sagittal'].active_section:
            if sec in self.gscenes['sagittal'].per_channel_pixmap_cached:
                continue
            try:
                fp = DataManager.get_image_filepath_v2(stack=self.stack, section=sec, prep_id=2, resol='lossless', version='contrastStretchedBlue')
            except Exception as e:
                sys.stderr.write('Section %d is invalid: %s\n' % (sec, str(e)))
                continue
            if not os.path.exists(fp):
                sys.stderr.write('Image %s does not exist.\n' % fp)
                continue
            qimage = QImage(fp)
            self.emit(SIGNAL('component_image_loaded(QImage, int)'), qimage, sec)


class BrainLabelingGUI(QMainWindow, Ui_BrainLabelingGui):
# class BrainLabelingGUI(QMainWindow, Ui_RectificationGUI):

    def __init__(self, parent=None, stack=None, first_sec=None, last_sec=None, downsample=None, img_version=None, prep_id=None):
        """
        Initialization of BrainLabelingGUI.
        """

        # t0 = time.time()

        # self.app = QApplication(sys.argv)
        QMainWindow.__init__(self, parent)

        self.stack = stack
        self.sagittal_downsample = downsample
        self.prep_id = prep_id

        self.setupUi(self)

        self.button_save.clicked.connect(self.save_contours)
        self.button_saveMarkers.clicked.connect(self.save_markers)
        self.button_saveStructures.clicked.connect(self.save_structures)
        self.button_saveProbStructures.clicked.connect(self.save_prob_structures)
        self.button_load.clicked.connect(self.load_contours)
        self.button_loadMarkers.clicked.connect(self.load_markers)
        self.button_loadStructures.clicked.connect(self.load_structures)
        self.button_loadProbStructures.clicked.connect(self.load_prob_structures)
        self.button_loadWarpedAtlas.clicked.connect(self.load_warped_atlas_volume)
        self.button_loadUnwarpedAtlas.clicked.connect(self.load_unwarped_atlas_volume)
        self.button_inferSide.clicked.connect(self.infer_side)
        self.button_displayOptions.clicked.connect(self.select_display_options)
        self.button_displayStructures.clicked.connect(self.select_display_structures)
        self.lineEdit_username.returnPressed.connect(self.username_changed)

        self.structure_volumes = defaultdict(dict)
        # self.structure_adjustments_3d = defaultdict(list)
        self.prob_structure_volumes = defaultdict(dict)

        self.volume_cache = {}
        # for ds in [8, 32]:
        for ds in [32]:
            try:
                # self.volume_cache[ds] = DataManager.load_intensity_volume_v2(self.stack, downscale=ds, prep_id=1)
                self.volume_cache[ds] = DataManager.load_intensity_volume_v2(self.stack, downscale=ds, prep_id=4)
                print self.volume_cache[ds].shape
            except:
                sys.stderr.write('Intensity volume of downsample %d does not exist.\n' % ds)

        self.splitter.setSizes([500, 500, 500])
        self.splitter_2.setSizes([1000, 500])

        self.sagittal_tb_gscene = DrawableZoomableBrowsableGraphicsScene_ForLabeling(id='sagittal_tb', gui=self, gview=self.sagittal_tb_gview)
        self.sagittal_tb_gview.setScene(self.sagittal_tb_gscene)

        self.coronal_gscene = DrawableZoomableBrowsableGraphicsScene_ForLabeling(id='coronal', gui=self, gview=self.coronal_gview)
        self.coronal_gview.setScene(self.coronal_gscene)

        self.horizontal_gscene = DrawableZoomableBrowsableGraphicsScene_ForLabeling(id='horizontal', gui=self, gview=self.horizontal_gview)
        self.horizontal_gview.setScene(self.horizontal_gscene)

        self.sagittal_gscene = DrawableZoomableBrowsableGraphicsScene_ForLabeling(id='sagittal', gui=self, gview=self.sagittal_gview)
        self.sagittal_gview.setScene(self.sagittal_gscene)

        self.sagittal_gscene.set_default_line_width(5)
        self.sagittal_gscene.set_default_line_color('b')
        self.sagittal_gscene.set_default_vertex_radius(10)
        self.sagittal_gscene.set_default_vertex_color('r')

        self.gscenes = {'coronal': self.coronal_gscene, 'sagittal': self.sagittal_gscene, 'horizontal': self.horizontal_gscene,
        'sagittal_tb': self.sagittal_tb_gscene}

        for gscene in self.gscenes.itervalues():
            gscene.drawings_updated.connect(self.drawings_updated)
            gscene.crossline_updated.connect(self.crossline_updated)
            gscene.active_image_updated.connect(self.active_image_updated)
            gscene.structure_volume_updated.connect(self.update_structure_volume)
            gscene.prob_structure_volume_updated.connect(self.update_prob_structure_volume)
            gscene.set_structure_volumes(self.structure_volumes)
            gscene.set_prob_structure_volumes(self.prob_structure_volumes)
            # gscene.set_drawings(self.drawings)

        # from functools import partial
        # self.gscenes['sagittal'].set_conversion_func_section_to_z(partial(DataManager.convert_section_to_z, stack=self.stack, z_begin=))
        # self.gscenes['sagittal'].set_conversion_func_z_to_section(partial(DataManager.convert_z_to_section, stack=self.stack))

        ##################
        # self.slider_downsample.valueChanged.connect(self.downsample_factor_changed)

        ###################
        self.contextMenu_set = True

        self.recent_labels = []

        self.structure_names = load_structure_names(os.environ['REPO_DIR']+'/gui/structure_names.txt')
        self.new_labelnames = load_structure_names(os.environ['REPO_DIR']+'/gui/newStructureNames.txt')
        self.structure_names = OrderedDict(sorted(self.new_labelnames.items()) + sorted(self.structure_names.items()))

        self.installEventFilter(self)

        # first_sec0, last_sec0 = DataManager.load_cropbox(self.stack)[4:]
        if self.prep_id == 3:
            first_sec0, last_sec0 = DataManager.load_cropbox_thalamus(self.stack)[4:]
        elif self.prep_id == 2:
            first_sec0, last_sec0 = DataManager.load_cropbox(self.stack)[4:]
        else:
            raise

        self.sections = range(first_sec0, last_sec0 + 1)

        image_feeder = ImageDataFeeder_v2('image feeder', stack=self.stack, sections=self.sections,
        prep_id=self.prep_id, use_data_manager=False,
        downscale=self.sagittal_downsample,
        version=img_version)
        image_feeder.set_orientation('sagittal')

        self.gscenes['sagittal'].set_data_feeder(image_feeder)

        self.connect(self.gscenes['sagittal'], SIGNAL("image_loaded(int)"), self.image_loaded)

        # self.button_stop.clicked.connect(self.read_images_thread.terminate)

        volume_resection_feeder = VolumeResectionDataFeeder('volume resection feeder', self.stack)

        if hasattr(self, 'volume_cache') and self.volume_cache is not None:

            coronal_volume_resection_feeder = VolumeResectionDataFeeder('coronal resection feeder', self.stack)
            coronal_volume_resection_feeder.set_volume_cache(self.volume_cache)
            coronal_volume_resection_feeder.set_orientation('coronal')
            coronal_volume_resection_feeder.set_downsample_factor(32)
            # coronal_volume_resection_feeder.set_downsample_factor(8)
            print coronal_volume_resection_feeder.x_dim, coronal_volume_resection_feeder.y_dim, coronal_volume_resection_feeder.z_dim
            self.gscenes['coronal'].set_data_feeder(coronal_volume_resection_feeder)
            self.gscenes['coronal'].set_active_i(50)

            horizontal_volume_resection_feeder = VolumeResectionDataFeeder('horizontal resection feeder', self.stack)
            horizontal_volume_resection_feeder.set_volume_cache(self.volume_cache)
            horizontal_volume_resection_feeder.set_orientation('horizontal')
            horizontal_volume_resection_feeder.set_downsample_factor(32)
            # horizontal_volume_resection_feeder.set_downsample_factor(8)
            self.gscenes['horizontal'].set_data_feeder(horizontal_volume_resection_feeder)
            self.gscenes['horizontal'].set_active_i(150)

            sagittal_volume_resection_feeder = VolumeResectionDataFeeder('sagittal resection feeder', self.stack)
            sagittal_volume_resection_feeder.set_volume_cache(self.volume_cache)
            sagittal_volume_resection_feeder.set_orientation('sagittal')
            sagittal_volume_resection_feeder.set_downsample_factor(32)
            # sagittal_volume_resection_feeder.set_downsample_factor(8)
            self.gscenes['sagittal_tb'].set_data_feeder(sagittal_volume_resection_feeder)
            self.gscenes['sagittal_tb'].set_active_i(150)

        try:
            self.gscenes['sagittal'].set_active_section(first_sec)
        except Exception as e:
            # sys.stderr.write(e.message + '\n')
            pass

        ##############################
        # Internal structure volumes #
        ##############################

        # Set the downsample factor for the structure volumes.
        # Try to match the highest resolution among all gviews, but upper limit is 1/8.
        self.volume_downsample_factor = max(8, np.min([gscene.data_feeder.downsample for gscene in self.gscenes.itervalues()]))
        for gscene in self.gscenes.values():
            gscene.set_structure_volumes_downscale_factor(self.volume_downsample_factor)


        #####################################
        # Internal structure volumes (prob) #
        #####################################

        # Set the downsample factor for the structure volumes.
        # Try to match the highest resolution among all gviews, but upper limit is 1/8.
        self.prob_volume_downsample_factor = 32
        for gscene in self.gscenes.values():
            gscene.set_prob_structure_volumes_downscale_factor(self.prob_volume_downsample_factor)

        #####################
        # Load R/G/B images #
        #####################

        # self.read_component_images_thread = ReadRGBComponentImagesThread(stack=self.stack, sections=range(first_sec, last_sec+1))
        # self.connect(self.read_component_images_thread, SIGNAL("component_image_loaded(QImage, int)"), self.component_image_loaded)
        # self.read_component_images_thread.start()

        #####################################
        # Set global origins of each gscene #
        #####################################

        # WholebrainAlignedPadded is defined as the domain after alignment, uncropped in xy, UNcropped at z.

        if self.prep_id == 3: # thalamus only
            lossless_image_cropboxXY_wrt_WholebrainAlignedPadded_tbResol = DataManager.load_cropbox_thalamus(stack=self.stack)[:4]
        elif self.prep_id == 2:
            lossless_image_cropboxXY_wrt_WholebrainAlignedPadded_tbResol = DataManager.load_cropbox(stack=self.stack)[:4]
        else:
            raise

        fp = DataManager.get_intensity_volume_bbox_filepath_v2(stack=self.stack, prep_id=4)
        download_from_s3(fp)
        thumbnail_image_cropbox_wrt_WholebrainAlignedPadded_tbResol = np.loadtxt(fp)
        print 'thumbnail_image_cropbox_wrt_WholebrainAlignedPadded_tbResol=', thumbnail_image_cropbox_wrt_WholebrainAlignedPadded_tbResol

        # Record the appropriate coordinate origin for this gscene.
        # The coordinate is wrt to origin of "whole brain aligned and padded volume", in thumbnail resolution (1/32 of raw).
        self.image_origin_wrt_WholebrainAlignedPadded_tbResol = {}
        self.image_origin_wrt_WholebrainAlignedPadded_tbResol['sagittal'] = \
        np.array((lossless_image_cropboxXY_wrt_WholebrainAlignedPadded_tbResol[0],
        lossless_image_cropboxXY_wrt_WholebrainAlignedPadded_tbResol[2],
        0))
        for gid in ['coronal', 'horizontal', 'sagittal_tb']:
            self.image_origin_wrt_WholebrainAlignedPadded_tbResol[gid] = \
            np.array((thumbnail_image_cropbox_wrt_WholebrainAlignedPadded_tbResol[0],
            thumbnail_image_cropbox_wrt_WholebrainAlignedPadded_tbResol[2],
            thumbnail_image_cropbox_wrt_WholebrainAlignedPadded_tbResol[4]))

    @pyqtSlot(int)
    def image_loaded(self, sec):
        """
        """
        gscene_id = self.sender().id
        gscene = self.gscenes[gscene_id]

        if gscene.active_section == sec:
            gscene.update_image()

        self.statusBar().showMessage('Image %d loaded.\n' % sec)
        print 'Image', sec, 'received.'

    @pyqtSlot(object, int)
    def component_image_loaded(self, qimage_blue, sec):
        """
        Callback for when R/G/B images are loaded.

        Args:
            qimage (QImage): the image
            sec (int): section
        """

        self.gscenes['sagittal'].per_channel_pixmap_cached[sec] = qimage_blue
        self.statusBar().showMessage('R/G/B images %d loaded.\n' % sec)
        print 'R/G/B images', sec, 'received.'

    @pyqtSlot()
    def username_changed(self):
        self.username = str(self.sender().text())
        print 'username changed to', self.username

    def get_username(self):
        if not hasattr(self, 'username') or self.username is None:
            username, okay = QInputDialog.getText(self, "Username", "Please enter your username:", QLineEdit.Normal, 'anon')
            if not okay: return
            self.username = str(username)
            self.lineEdit_username.setText(self.username)

        return self.username

    def structure_tree_changed(self, item, column):

        tree_widget = self.sender()
        complete_name = str(item.text(column))
        abbr = re.findall('^.*?(\((.*)\))?$', complete_name)[0][1]

        check_state = item.checkState(column)
        if check_state == Qt.Unchecked:

            for gscene in self.gscenes.values():
                for section_index, polygons in gscene.drawings.iteritems():
                    for polygon in polygons:
                        if polygon.label == abbr:
                            polygon.setVisible(False)

        elif check_state == Qt.PartiallyChecked:
            pass
        elif check_state == Qt.Checked:
            for gscene in self.gscenes.values():
                for section_index, polygons in gscene.drawings.iteritems():
                    for polygon in polygons:
                        if polygon.label == abbr:
                            polygon.setVisible(True)
        else:
            raise Exception('Unknown check state.')

        # selected_items = tree_widget.selectedItems()
        # print [str(it.text(0)) for it in selected_items]


    @pyqtSlot()
    def select_display_structures(self):
        loaded_structure_abbrs = set([convert_to_unsided_label(name_s) for name_s in self.gscenes['sagittal'].get_label_section_lookup().keys()])

        structure_tree_dict = json.load(open('structure_tree.json'))
        # structure_tree_dict = {name: d for name, d in structure_tree_dict_all.iteritems() if d['abbr'] in loaded_structure_names}
        # structure_tree_names = {'brainstem': {}}

        def structure_entry_to_str(node):
            if 'abbr' in node and len(node['abbr']) > 0:
                key = node['fullname'] + ' (' + node['abbr'] + ')'
            else:
                key = node['fullname']
            return key

        def get_children_names(name):
            node = structure_tree_dict[name]
            key = structure_entry_to_str(node)
            return (key, dict([get_children_names(child_name) for child_name in node['children']]))

        structure_name_tree = dict([get_children_names('brainstem')])

        # extract_names(structure_tree_names['brainstem'], structure_tree_dict['brainstem'], structure_tree_dict)
        # structure_tree_names = {'midbrain': ['IC', 'SC'], 'hindbrain': {'pons': ['7N', '5N'], 'medulla': ['7n', 'SCP']}}

        display_structures_widget = QDialog(self)

        tree_widget = QTreeWidget(display_structures_widget)
        tree_widget.setHeaderLabels(['Structures'])
        fill_tree_widget(tree_widget, structure_name_tree, loaded_structure_abbrs)
        # tree_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tree_widget.setMinimumHeight(1000)
        tree_widget.setMinimumWidth(500)

        # http://stackoverflow.com/questions/27521391/signal-a-qtreewidgetitem-toggled-checkbox
        tree_widget.itemChanged.connect(self.structure_tree_changed)

        dialog_layout = QVBoxLayout(display_structures_widget)
        dialog_layout.addWidget(tree_widget)
        display_structures_widget.setLayout(dialog_layout)
        # display_structures_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        display_structures_widget.setWindowTitle("Select structures to show")
        # display_structures_widget.exec_()
        display_structures_widget.show()

    # @pyqtSlot()
    # def select_display_structures(self):
    #
    #     display_structures_widget = QDialog(self)
    #
    #     scroll = QScrollArea(display_structures_widget)
    #
    #     viewport = QWidget(display_structures_widget)
    #     scroll.setWidget(viewport)
    #     scroll.setWidgetResizable(True)
    #
    #     viewport_layout = QVBoxLayout(viewport)
    #
    #     structure_names = set([convert_name_to_unsided(name_s) for name_s in self.gscenes['sagittal'].get_label_section_lookup().keys()])
    #
    #     if not hasattr(self, 'show_structure'):
    #         self.show_structure = {}
    #
    #     for name in sorted(structure_names):
    #         if name not in self.show_structure:
    #             self.show_structure[name] = True
    #
    #         checkbox_showStructure = QCheckBox(name)
    #         checkbox_showStructure.setChecked(self.show_structure[name])
    #         checkbox_showStructure.stateChanged.connect(self.checkbox_showStructure_callback)
    #         viewport_layout.addWidget(checkbox_showStructure)
    #
    #     viewport.setLayout(viewport_layout)
    #
    #     dialog_layout = QVBoxLayout(display_structures_widget)
    #     dialog_layout.addWidget(scroll)
    #     display_structures_widget.setLayout(dialog_layout)
    #
    #     display_structures_widget.setWindowTitle("Select structures to show")
    #     # display_structures_widget.exec_()
    #     display_structures_widget.show()


    # def checkbox_showStructure_callback(self, checked):
    #     name = str(self.sender().text())
    #     self.show_structure[name] = bool(checked)
    #
    #     for gscene in self.gscenes.values():
    #         for section_index, polygons in gscene.drawings.iteritems():
    #             for polygon in polygons:
    #                 if polygon.label == name:
    #                     polygon.setVisible(bool(checked))

    @pyqtSlot()
    def select_display_options(self):

        if not hasattr(self, 'show_polygons'):
            self.show_polygons = True
            self.show_vertices = True
            self.show_labels = True
            self.hide_interpolated = False

        display_option_widget = QDialog(self)

        layout = QVBoxLayout()

        checkbox_showPolygons = QCheckBox("Polygon")
        checkbox_showPolygons.setChecked(self.show_polygons)
        checkbox_showPolygons.stateChanged.connect(self.checkbox_showPolygons_callback)
        layout.addWidget(checkbox_showPolygons)

        checkbox_showVertices = QCheckBox("Vertices")
        checkbox_showVertices.setChecked(self.show_vertices)
        checkbox_showVertices.stateChanged.connect(self.checkbox_showVertices_callback)
        layout.addWidget(checkbox_showVertices)

        checkbox_showLabels = QCheckBox("Labels")
        checkbox_showLabels.setChecked(self.show_labels)
        checkbox_showLabels.stateChanged.connect(self.checkbox_showLabels_callback)
        layout.addWidget(checkbox_showLabels)

        checkbox_hideInterpolated = QCheckBox("Hide interpolated")
        checkbox_hideInterpolated.setChecked(self.hide_interpolated)
        checkbox_hideInterpolated.stateChanged.connect(self.checkbox_hideInterpolated_callback)
        layout.addWidget(checkbox_hideInterpolated)

        display_option_widget.setLayout(layout)
        display_option_widget.setWindowTitle("Select display options")
        display_option_widget.exec_()

    @pyqtSlot(int)
    def checkbox_showLabels_callback(self, checked):
        self.show_labels = checked
        for gscene in self.gscenes.itervalues():
            for section_index, polygons in gscene.drawings.iteritems():
                for polygon in polygons:
                    polygon.properties['label_textItem'].setVisible(checked)

    @pyqtSlot(int)
    def checkbox_showVertices_callback(self, checked):
        self.show_vertices = checked
        for gscene in self.gscenes.itervalues():
            for section_index, polygons in gscene.drawings.iteritems():
                for polygon in polygons:
                    for v in polygon.vertex_circles:
                        v.setVisible(checked)

    @pyqtSlot(int)
    def checkbox_showPolygons_callback(self, checked):
        self.show_polygons = checked
        for gscene in self.gscenes.itervalues():
            for section_index, polygons in gscene.drawings.iteritems():
                for polygon in polygons:
                    polygon.setVisible(checked)

    @pyqtSlot(int)
    def checkbox_hideInterpolated_callback(self, checked):
        self.hide_interpolated = checked
        for gscene in self.gscenes.itervalues():
            for section_index, polygons in gscene.drawings.iteritems():
                for polygon in polygons:
                    if polygon.type != 'confirmed':
                        polygon.setVisible(not bool(checked))

    @pyqtSlot()
    def infer_side(self):
        self.gscenes['sagittal'].infer_side()
        self.gscenes['sagittal_tb'].infer_side()
        self.gscenes['coronal'].infer_side()
        self.gscenes['horizontal'].infer_side()
    #
    # def merge_contour_entries(self, new_entries_df):
    #     """
    #     Merge new entries into loaded entries.
    #     new_entries: dict. {polygon_id: entry}FileName
    #     Return: new dict.
    #     """
    #
    #     self.contour_df_loaded.update(new_entries_df)

    @pyqtSlot()
    def save_markers(self):
        """
        Save markers.
        """

        timestamp = datetime.now().strftime("%m%d%Y%H%M%S")

        sagittal_markers_curr_session = self.gscenes['sagittal'].convert_drawings_to_entries(timestamp=timestamp, username=self.username, classes=['neuron'])
        sagittal_markers_original = convert_annotation_v3_aligned_cropped_to_original(DataFrame(sagittal_markers_curr_session).T, stack=self.stack,
        prep_id=self.prep_id)
        sagittal_markers_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=True, suffix='neurons', timestamp=timestamp)
        save_hdf_v2(sagittal_markers_original, sagittal_markers_fp)
        upload_to_s3(sagittal_markers_fp)
        print 'Sagittal markers saved to %s.' % sagittal_markers_fp
        self.statusBar().showMessage('Sagittal markers saved to %s.' % sagittal_markers_fp)

    @pyqtSlot()
    def save_structures(self):
        """
        Save 3D structure volumes.
        """

        # timestamp = datetime.now().strftime("%m%d%Y%H%M%S")
        import uuid

        entries = {}
        for (name, side), v in self.structure_volumes.iteritems():
            entry = {}
            # entry['volume_in_bbox'] = v['volume_in_bbox']
            entry['volume_in_bbox'] = bp.pack_ndarray_str(v['volume_in_bbox'])
            entry['bbox'] = v['bbox']
            entry['name'] = name
            entry['side'] = side
            if 'edits' not in v or v['edits'] is None or len(v['edits']) == 0:
                entry['edits'] = []
            else:
                entry['edits'] = v['edits']
            #     entry['edits'] =  [{'type': 'creation', 'username':self.username, 'timestamp':timestamp}]
            # else:

            if hasattr(v, 'structure_id') and v.properties['structure_id'] is not None:
                structure_id = v.properties['structure_id']
            else:
                structure_id = str(uuid.uuid4().fields[-1])

            entries[structure_id] = entry

        structure_df = DataFrame(entries).T
        structure_df_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=True, suffix='structures', timestamp='now')
        save_hdf_v2(structure_df, structure_df_fp)
        upload_to_s3(structure_df_fp)
        print '3D structures saved to %s.' % structure_df_fp


    @pyqtSlot()
    def save_prob_structures(self):
        """
        Save probabilistic structure volumes.
        """

        # timestamp = datetime.now().strftime("%m%d%Y%H%M%S")
        import uuid

        entries = {}
        for (name, side), v in self.prob_structure_volumes.iteritems():
            entry = {}
            # entry['volume_in_bbox'] = v['volume_in_bbox']
            entry['volume_in_bbox'] = bp.pack_ndarray_str(v['volume_in_bbox'])
            entry['bbox'] = v['bbox']
            entry['name'] = name
            entry['side'] = side
            if 'edits' not in v or v['edits'] is None or len(v['edits']) == 0:
                entry['edits'] = []
            else:
                entry['edits'] = v['edits']
            #     entry['edits'] =  [{'type': 'creation', 'username':self.username, 'timestamp':timestamp}]
            # else:

            if hasattr(v, 'structure_id') and v.properties['structure_id'] is not None:
                structure_id = v.properties['structure_id']
            else:
                structure_id = str(uuid.uuid4().fields[-1])

            entries[structure_id] = entry

        structure_df = DataFrame(entries).T
        structure_df_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=True, suffix='probStructures', timestamp='now')
        save_hdf_v2(structure_df, structure_df_fp)
        upload_to_s3(structure_df_fp)
        print 'Probabilistic structures saved to %s.' % structure_df_fp


    @pyqtSlot()
    def save_contours(self):
        """
        Save structure boundaries.
        """

        timestamp = datetime.now().strftime("%m%d%Y%H%M%S")

        # Save sagittal
        sagittal_contour_entries_curr_session = self.gscenes['sagittal'].convert_drawings_to_entries(timestamp=timestamp, username=self.username)
        sagittal_contours_df_original = convert_annotation_v3_aligned_cropped_to_original(DataFrame(sagittal_contour_entries_curr_session).T,
        stack=self.stack, in_downsample=self.gscenes['sagittal'].data_feeder.downsample, prep_id=self.prep_id)
        sagittal_contours_df_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=True, suffix='contours', timestamp=timestamp)
        # sagittal_contours_df_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=False, stack_m=stack_m,
        #                                                        classifier_setting_m=classifier_setting_m,
        #                                                       classifier_setting_f=classifier_setting_f,
        #                                                       warp_setting=warp_setting, suffix='contours')
        save_hdf_v2(sagittal_contours_df_original, sagittal_contours_df_fp)
        upload_to_s3(sagittal_contours_df_fp)
        self.statusBar().showMessage('Sagittal boundaries saved to %s.' % sagittal_contours_df_fp)
        print 'Sagittal boundaries saved to %s.' % sagittal_contours_df_fp

        # Save coronal
        # coronal_contour_entries_curr_session = self.gscenes['coronal'].convert_drawings_to_entries(timestamp=timestamp, username=self.username)
        # # print coronal_contour_entries_curr_session
        # if len(coronal_contour_entries_curr_session) > 0:
        #     # coronal_contours_df_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=False, stack_m=stack_m,
        #     #                                                        classifier_setting_m=classifier_setting_m,
        #     #                                                       classifier_setting_f=classifier_setting_f,
        #     #                                                       warp_setting=warp_setting, suffix='contours_coronal')
        #     coronal_contours_df_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=True, suffix='contours_coronal', timestamp=timestamp)
        #     save_hdf_v2(coronal_contour_entries_curr_session, coronal_contours_df_fp)
        #     upload_to_s3(coronal_contours_df_fp)
        #     self.statusBar().showMessage('Coronal boundaries saved to %s.' % coronal_contours_df_fp)
        #     print 'Coronal boundaries saved to %s.' % coronal_contours_df_fp

        # Save horizontal
        # horizontal_contour_entries_curr_session = self.gscenes['horizontal'].convert_drawings_to_entries(timestamp=timestamp, username=self.username)
        # if len(horizontal_contour_entries_curr_session) > 0:
        #     # horizontal_contours_df_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=False, stack_m=stack_m,
        #     #                                                        classifier_setting_m=classifier_setting_m,
        #     #                                                       classifier_setting_f=classifier_setting_f,
        #     #                                                       warp_setting=warp_setting, suffix='contours_horizontal')
        #     horizontal_contours_df_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=True, suffix='contours_horizontal', timestamp=timestamp)
        #     save_hdf_v2(horizontal_contour_entries_curr_session, horizontal_contours_df_fp)
        #     upload_to_s3(horizontal_contours_df_fp)
        #     self.statusBar().showMessage('Horizontal boundaries saved to %s.' % horizontal_contours_df_fp)
        #     print 'Horizontal boundaries saved to %s.' % horizontal_contours_df_fp

    @pyqtSlot()
    def load_markers(self):
        """
        """

        markers_df_fp = str(QFileDialog.getOpenFileName(self, "Choose marker annotation file", os.path.join(ANNOTATION_ROOTDIR, self.stack)))
        # download_from_s3(markers_df_fp)
        markers_df = load_hdf_v2(markers_df_fp)

        markers_df_cropped = convert_annotation_v3_original_to_aligned_cropped(markers_df, stack=self.stack, prep_id=self.prep_id)
        markers_df_cropped_sagittal = markers_df_cropped[(markers_df_cropped['orientation'] == 'sagittal') & (markers_df_cropped['downsample'] == self.gscenes['sagittal'].data_feeder.downsample)]

        # for i, marker_entry in markers_df_cropped_sagittal.iterrows():
        #     if 'label' not in marker_entry:
        #         print marker_entry

        self.gscenes['sagittal'].load_drawings(markers_df_cropped_sagittal, append=False, vertex_color=MARKER_COLOR_CHAR)

    def load_atlas_volume(self, warped=True):

        if not warped:
            atlas_volumes, atlas_bbox_wrt_MD589 = DataManager.load_original_volume_all_known_structures_v2(stack='atlasV5', return_label_mappings=False,
            name_or_index_as_key='name',
            # structures=['7N_L', '5N_L', 'SNR_L']
            structures=['IC']
            )

            xdim = atlas_bbox_wrt_MD589[1] - atlas_bbox_wrt_MD589[0]
            ydim = atlas_bbox_wrt_MD589[3] - atlas_bbox_wrt_MD589[2]
            zdim = atlas_bbox_wrt_MD589[5] - atlas_bbox_wrt_MD589[4]

            # unwarped_atlas_origin_wrt_wholeBrainAlignedXYCropped_volResol = np.array([0,0,0])
            # unwarped_atlas_origin_wrt_wholeBrainAlignedPadded_volResol = unwarped_atlas_origin_wrt_wholeBrainAlignedXYCropped_volResol + self.image_origin_wrt_WholebrainAlignedPadded_tbResol * 32. / self.prob_volume_downsample_factor
            atlas_bbox_wrt_wholeBrainAlignedPadded_volResol = np.array([0, xdim-1, 0, ydim-1, 0, zdim-1]) + \
                    self.image_origin_wrt_WholebrainAlignedPadded_tbResol['sagittal'][[0,0,1,1,2,2]] * 32. / self.prob_volume_downsample_factor

        else:
            if stack in ['MD661', 'MD662']:
                detector_id_f = 1
            elif stack in ['MD653', 'MD652', 'MD642', 'MD657', 'MD658']:
                detector_id_f = 13
            else:
                detector_id_f = 15

            atlas_volumes = DataManager.load_transformed_volume_all_known_structures(stack_m='atlasV5', stack_f=self.stack,
            warp_setting=17, prep_id_f=2, detector_id_f=detector_id_f,
            return_label_mappings=False,
            name_or_index_as_key='name',
            # structures=['7N_L', '5N_L', 'SNR_L']
            structures=['IC']
            )

            atlas_origin_wrt_wholeBrainAlignedPadded_tbResol = DataManager.load_cropbox(stack=self.stack, convert_section_to_z=True)[[0,2,4]]

            atlas_ydim_wrt_wholeBrainAlignedPadded_tbResol, \
            atlas_xdim_wrt_wholeBrainAlignedPadded_tbResol, \
            atlas_zdim_wrt_wholeBrainAlignedPadded_tbResol = atlas_volumes.values()[0].shape

            atlas_bbox_wrt_wholeBrainAlignedPadded_tbResol = np.array([atlas_origin_wrt_wholeBrainAlignedPadded_tbResol[0],
            atlas_origin_wrt_wholeBrainAlignedPadded_tbResol[0] + atlas_xdim_wrt_wholeBrainAlignedPadded_tbResol - 1,
            atlas_origin_wrt_wholeBrainAlignedPadded_tbResol[1],
            atlas_origin_wrt_wholeBrainAlignedPadded_tbResol[1] + atlas_ydim_wrt_wholeBrainAlignedPadded_tbResol - 1,
            atlas_origin_wrt_wholeBrainAlignedPadded_tbResol[2],
            atlas_origin_wrt_wholeBrainAlignedPadded_tbResol[2] + atlas_zdim_wrt_wholeBrainAlignedPadded_tbResol - 1])

            atlas_bbox_wrt_wholeBrainAlignedPadded_volResol = atlas_bbox_wrt_wholeBrainAlignedPadded_tbResol * 32. / self.prob_volume_downsample_factor

        from skimage.transform import rescale
        atlas_volumes = {name_s: rescale(v, self.sagittal_downsample) for name_s, v in atlas_volumes.iteritems()}
        atlas_bbox_wrt_wholeBrainAlignedPadded_volResol = atlas_bbox_wrt_wholeBrainAlignedPadded_volResol * self.sagittal_downsample

        for name_s, v in atlas_volumes.iteritems():
            name_u, side = parse_label(name_s)[:2]
            self.prob_structure_volumes[(name_u, side)] = {'volume_in_bbox': v, 'bbox': atlas_bbox_wrt_wholeBrainAlignedPadded_volResol}
            print 'Load', (name_u, side), self.prob_structure_volumes[(name_u, side)]['bbox']

            # Update drawings on all gscenes based on `prob_structure_volumes` that was just assigned.
            for gscene in self.gscenes.values():
                gscene.update_drawings_from_prob_structure_volume(name_u, side, levels=[0.5])

    @pyqtSlot()
    def load_unwarped_atlas_volume(self):
        """
        Load atlas volumes that are not aligned to subject.
        Initial pose is such that the origin of the atlas coincides with that of the subject volume.

        This populates the graphicsScenes with contours. Note that no volumes are reconstructed from them yet.
        """

        self.load_atlas_volume(warped=False)

    @pyqtSlot()
    def load_warped_atlas_volume(self):
        """
        Load warped atlas volumes.
        This populates the graphicsScenes with contours. Note that no volumes are reconstructed from them yet.
        """
        self.load_atlas_volume(warped=True)

    @pyqtSlot()
    def load_prob_structures(self):

        structures_df_fp = str(QFileDialog.getOpenFileName(self, "Choose the structure annotation file", os.path.join(ANNOTATION_ROOTDIR, self.stack)))
        # print structures_df_fp
        structure_df = load_hdf_v2(structures_df_fp)

        for sid, struct_entry in structure_df.iterrows():
            name_u = struct_entry['name']
            side = struct_entry['side']
            print name_u, side
            self.prob_structure_volumes[(name_u, side)] = {'bbox': struct_entry['bbox'],
            'volume_in_bbox': bp.unpack_ndarray_str(struct_entry['volume_in_bbox']),
            'edits': struct_entry['edits']}

        # from skimage.transform import rescale
        # atlas_volumes = {name_s: rescale(v, self.sagittal_downsample) for name_s, v in atlas_volumes.iteritems()}
        # atlas_bbox_wrt_wholeBrainAlignedPadded_volResol = atlas_bbox_wrt_wholeBrainAlignedPadded_volResol * self.sagittal_downsample

        # for name_s, v in atlas_volumes.iteritems():
        #     name_u, side = parse_label(name_s)[:2]
            # self.prob_structure_volumes[(name_u, side)] = {'volume_in_bbox': v, 'bbox': atlas_bbox_wrt_wholeBrainAlignedPadded_volResol}
        # print 'Load', (name_u, side), self.prob_structure_volumes[(name_u, side)]['bbox']

        # Update drawings on all gscenes based on `prob_structure_volumes` that was just assigned.
            for gscene in self.gscenes.values():
                gscene.update_drawings_from_prob_structure_volume(name_u, side, levels=[0.5])

    @pyqtSlot()
    def load_structures(self):
        """
        Load a 3D structure annotation file.
        The structure file stores a table: rows are structure IDs, columns are 3D structure properties.
        """

        structures_df_fp = str(QFileDialog.getOpenFileName(self, "Choose the structure annotation file", os.path.join(ANNOTATION_ROOTDIR, self.stack)))
        structure_df = load_hdf_v2(structures_df_fp)

        self.structure_df_loaded = structure_df
        for structure_id, structure_entry in structure_df.iterrows():

            if structure_entry['side'] is None:
                name_side_tuple = (structure_entry['name'], 'S')
            else:
                name_side_tuple = (structure_entry['name'], structure_entry['side'])

            if 'edits' in structure_entry:
                edits = structure_entry['edits']
            else:
                edits = []

            bbox_wrt_brainstem_volRes = structure_entry['bbox']

            bbox_wrt_wholebrain_volRes = bbox_wrt_brainstem_volRes + \
            np.array([self.image_origin_wrt_WholebrainAlignedPadded_tbResol['sagittal'][0] * 32. / self.volume_downsample_factor,
            self.image_origin_wrt_WholebrainAlignedPadded_tbResol['sagittal'][0] * 32. / self.volume_downsample_factor,
            self.image_origin_wrt_WholebrainAlignedPadded_tbResol['sagittal'][1] * 32. / self.volume_downsample_factor,
            self.image_origin_wrt_WholebrainAlignedPadded_tbResol['sagittal'][1] * 32. / self.volume_downsample_factor,
            self.image_origin_wrt_WholebrainAlignedPadded_tbResol['sagittal_tb'][2] * 32. / self.volume_downsample_factor,
            self.image_origin_wrt_WholebrainAlignedPadded_tbResol['sagittal_tb'][2] * 32. / self.volume_downsample_factor])

            self.structure_volumes[name_side_tuple] = {'volume_in_bbox': bp.unpack_ndarray_str(structure_entry['volume_in_bbox']).astype(np.bool),
                                        'bbox': bbox_wrt_wholebrain_volRes,
                                        'edits': edits,
                                        'structure_id': structure_id}

            print name_side_tuple, self.structure_volumes[name_side_tuple]['bbox']

            sys.stderr.write("Updating gscene contours for structure %s...\n" % str(name_side_tuple))
            # for gscene_id in self.gscenes:
            #     self.update_structure_volume(structure_entry['name'], structure_entry['side'], use_confirmed_only=False, recompute_from_contours=False)

            t = time.time()
            self.update_structure_volume(structure_entry['name'], structure_entry['side'], \
            use_confirmed_only=False, recompute_from_contours=False, \
            affected_gscenes=['sagittal', 'sagittal_tb', 'horizontal', 'coronal'])
            sys.stderr.write("Update gscene contours: %.2f seconds.\n" % (time.time()-t))

    @pyqtSlot()
    def load_contours(self):
        """
        Load contours.
        The contour file stores a table: rows are contour IDs, columns are polygon properties.
        """

        sagittal_contours_df_fp = str(QFileDialog.getOpenFileName(self, "Choose sagittal contour annotation file", os.path.join(ANNOTATION_ROOTDIR, self.stack)))
        sagittal_contours_df = load_hdf_v2(sagittal_contours_df_fp)
        sagittal_contours_df_cropped = convert_annotation_v3_original_to_aligned_cropped(sagittal_contours_df, stack=self.stack,\
                                        out_downsample=self.gscenes['sagittal'].data_feeder.downsample,
                                        prep_id=self.prep_id)
        sagittal_contours_df_cropped_sagittal = sagittal_contours_df_cropped[(sagittal_contours_df_cropped['orientation'] == 'sagittal') & (sagittal_contours_df_cropped['downsample'] == self.gscenes['sagittal'].data_feeder.downsample)]
        self.gscenes['sagittal'].load_drawings(sagittal_contours_df_cropped_sagittal, append=False)

    @pyqtSlot()
    def active_image_updated(self):
        self.setWindowTitle('BrainLabelingGUI, stack %(stack)s, fn %(fn)s, section %(sec)d, z=%(z).2f, x=%(x).2f, y=%(y).2f' % \
        dict(stack=self.stack,
        sec=self.gscenes['sagittal'].active_section
        if self.gscenes['sagittal'].active_section is not None else -1,
        fn=metadata_cache['sections_to_filenames'][self.stack][self.gscenes['sagittal'].active_section] \
        if self.gscenes['sagittal'].active_section is not None else '',
        z=self.gscenes['sagittal'].active_i,
        x=self.gscenes['coronal'].active_i if self.gscenes['coronal'].active_i is not None else 0,
        y=self.gscenes['horizontal'].active_i if self.gscenes['horizontal'].active_i is not None else 0))

    @pyqtSlot(int, int, int, str)
    def crossline_updated(self, cross_x_lossless, cross_y_lossless, cross_z_lossless, source_gscene_id):
        print 'GUI: update all crosses to', cross_x_lossless, cross_y_lossless, cross_z_lossless, 'from', source_gscene_id

        for gscene_id, gscene in self.gscenes.iteritems():
            # if gscene_id == source_gscene_id: # Skip updating the crossline if the update is triggered from this gscene
            #     continue
            if gscene.mode == 'crossline':
                try:
                    gscene.update_cross(cross_x_lossless, cross_y_lossless, cross_z_lossless,
                    origin=self.image_origin_wrt_WholebrainAlignedPadded_tbResol[gscene_id]*32.)
                except Exception as e:
                    sys.stderr.write(str(e) + '\n')

    @pyqtSlot(object)
    def drawings_updated(self, polygon):
        print 'Drawings updated.'
        # self.save()

        # sagittal_label_section_lookup = self.gscenes['sagittal'].get_label_section_lookup()
        # labels = sagittal_label_section_lookup.keys()

        # self.gscenes['coronal'].get_label_section_lookup()
        # self.gscenes['horizontal'].get_label_section_lookup()


    @pyqtSlot(str, str, bool, bool)
    def update_structure_volume(self, name_u, side, use_confirmed_only, recompute_from_contours, from_gscene_id=None, affected_gscenes=None):
        """
        This function is triggered by `structure_volume_updated` signal from a gscene.

        - Retrieve the volumes stored internally for each view.
        The volumes in different views are potentially different.
        - Compute the average volume across all views.
        - Use this average volume to update the stored version in each view.

        Args:
            use_confirmed_only (bool): If True, when reconstructing the volume, only use confirmed contours.
            recompute_from_contours (bool): Set to True, if want to re-compute the volume based on contours,
            replacing the volume in `self.structure_volumes` if it already exists.
            Set to False, if `self.structure_volumes` already stores the new volume and therefore
            calling this function is just to update the contours.
            from_gscene_id (str):
            affected_gscenes (list of str):
        """

        # Arguments passed in are Qt Strings. This guarantees they are python str.
        name_u = str(name_u)
        side = str(side)

        # Reconstruct the volume for each gview.
        # Only interpolate between confirmed contours.

        # volumes_3view = {}
        # bboxes_3view = {}

        # for gscene_id, gscene in self.gscenes.iteritems():

        if (name_u, side) not in self.structure_volumes or recompute_from_contours:

            print 'Re-computing volume of %s from contours.' % str((name_u, side))
            if from_gscene_id is None:
                assert self.sender() is not None, Exception("Cannot infer the interpolation direction. Must provide from_gscene_id or call as a slot.")
                from_gscene_id = self.sender().id

            gscene = self.gscenes[from_gscene_id]

            if use_confirmed_only:
                matched_confirmed_polygons = [p for i, polygons in gscene.drawings.iteritems() for p in polygons \
                                    if p.properties['label'] == name_u and \
                                    p.properties['side'] == side and \
                                    p.properties['type'] == 'confirmed']
            else:
                matched_confirmed_polygons = [p for i, polygons in gscene.drawings.iteritems() for p in polygons \
                if p.properties['label'] == name_u and p.properties['side'] == side]

            if len(matched_confirmed_polygons) < 2:
                sys.stderr.write('%s: Cannot interpolate because there are fewer than two confirmed polygons for structure %s.\n' % (from_gscene_id, (name_u, side)))
                return

            factor_dataResol_to_volResol = float(gscene.data_feeder.downsample) / self.volume_downsample_factor

            if from_gscene_id == 'sagittal' or from_gscene_id == 'sagittal_tb':
                # keys are depth coordinates, wrt the origin of "whole brain aligned and padded volume", in internal structure resolution.
                # values are 2D contour vertex coordinates, wrt the origin of "whole brain aligned and padded volume", in internal structure resolution.

                contour_points_grouped_by_pos_wrt_WholebrainAlignedPadded_volResol = {p.properties['position_um'] / (XY_PIXEL_DISTANCE_LOSSLESS * self.volume_downsample_factor): \
                                                [((c.scenePos().x() * gscene.data_feeder.downsample + \
                                                    self.image_origin_wrt_WholebrainAlignedPadded_tbResol[from_gscene_id][0] * 32.) / float(self.volume_downsample_factor),
                                                (c.scenePos().y() * gscene.data_feeder.downsample + \
                                                    self.image_origin_wrt_WholebrainAlignedPadded_tbResol[from_gscene_id][1] * 32.) / float(self.volume_downsample_factor))
                                                for c in p.vertex_circles]
                                                for p in matched_confirmed_polygons}

                for p in matched_confirmed_polygons:
                    print 'z =', p.properties['position_um'] / (XY_PIXEL_DISTANCE_LOSSLESS * self.volume_downsample_factor)
                    for c in p.vertex_circles:
                        print c.scenePos().x() * gscene.data_feeder.downsample, self.image_origin_wrt_WholebrainAlignedPadded_tbResol[from_gscene_id][0] * 32., self.volume_downsample_factor
                        print c.scenePos().y() * gscene.data_feeder.downsample, self.image_origin_wrt_WholebrainAlignedPadded_tbResol[from_gscene_id][1] * 32., self.volume_downsample_factor

                volume_volResol, bbox_wrt_WholebrainAlignedPadded_volResol = interpolate_contours_to_volume(contour_points_grouped_by_pos_wrt_WholebrainAlignedPadded_volResol, 'z')

            elif from_gscene_id == 'coronal':
                contour_points_grouped_by_pos = {p.properties['position_um'] / (XY_PIXEL_DISTANCE_LOSSLESS * self.volume_downsample_factor): \
                                                [(c.scenePos().y() * factor_dataResol_to_volResol,
                                                (gscene.data_feeder.z_dim - 1 - c.scenePos().x()) * factor_dataResol_to_volResol)
                                                for c in p.vertex_circles]
                                                for p in matched_confirmed_polygons}
                volume, bbox = interpolate_contours_to_volume(contour_points_grouped_by_pos, 'x')
                # self.gscenes[gscene_id].structure_volumes[(name_u, side)] = volume, bbox
                # self.structure_volumes[(name_u, side)] = interpolate_contours_to_volume(contour_points_grouped_by_pos, 'x')

            elif from_gscene_id == 'horizontal':
                contour_points_grouped_by_pos = {p.properties['position_um'] / (XY_PIXEL_DISTANCE_LOSSLESS * self.volume_downsample_factor): \
                                                [(c.scenePos().x() * factor_dataResol_to_volResol,
                                                (gscene.data_feeder.z_dim - 1 - c.scenePos().y()) * factor_dataResol_to_volResol)
                                                for c in p.vertex_circles]
                                                for p in matched_confirmed_polygons}
                volume, bbox = interpolate_contours_to_volume(contour_points_grouped_by_pos, 'y')
                # self.gscenes[gscene_id].structure_volumes[(name_u, side)] = volume, bbox
                # self.gscenes[gscene_id].structure_volumes[(name_u, side)] = interpolate_contours_to_volume(contour_points_grouped_by_pos, 'y')
                # self.structure_volumes[(name_u, side)] = interpolate_contours_to_volume(contour_points_grouped_by_pos, 'y')

            self.structure_volumes[(name_u, side)]['volume_in_bbox'] = volume_volResol
            self.structure_volumes[(name_u, side)]['bbox'] = bbox_wrt_WholebrainAlignedPadded_volResol
            print 'Internal structures:', (name_u, side), self.structure_volumes[(name_u, side)]['bbox']

            # volumes_3view[gscene_id] = volume
            # bboxes_3view[gscene_id] = bbox

        # self.structure_volumes[(name_u, side)] = \
        # average_multiple_volumes(volumes_3view.values(), bboxes_3view.values())
        # self.structure_volumes[(name_u, side)] = self.gscenes['sagittal'].structure_volumes[(name_u, side)]

        if affected_gscenes is None:
            affected_gscenes = self.gscenes.keys()

        for gscene_id in affected_gscenes:
            self.gscenes[gscene_id].update_drawings_from_structure_volume(name_u, side)

        print '3D structure updated.'
        self.statusBar().showMessage('3D structure updated.')


    @pyqtSlot(str, str)
    def update_prob_structure_volume(self, name_u, side, from_gscene_id=None, affected_gscenes=None):
        """
        This function is triggered by `prob_structure_volume_updated` signal from a gscene.
        """

        # Arguments passed in are Qt Strings. This guarantees they are python str.
        name_u = str(name_u)
        side = str(side)

        if affected_gscenes is None:
            affected_gscenes = self.gscenes.keys()

        for gscene_id in affected_gscenes:
        # for gscene_id in ['sagittal']:
            self.gscenes[gscene_id].update_drawings_from_prob_structure_volume(name_u, side, levels=[.5])

        print '3D prob structure updated.'
        self.statusBar().showMessage('3D prob structure updated.')

    def eventFilter(self, obj, event):
        # print obj.metaObject().className(), event.type()

        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_1:
                self.gscenes['sagittal'].show_previous()
            elif key == Qt.Key_2:
                self.gscenes['sagittal'].show_next()
            elif key == Qt.Key_3:
                self.gscenes['coronal'].show_previous()
            elif key == Qt.Key_4:
                self.gscenes['coronal'].show_next()
            elif key == Qt.Key_5:
                self.gscenes['horizontal'].show_previous()
            elif key == Qt.Key_6:
                self.gscenes['horizontal'].show_next()
            elif key == Qt.Key_7:
                self.gscenes['sagittal_tb'].show_previous()
            elif key == Qt.Key_8:
                self.gscenes['sagittal_tb'].show_next()

            elif key == Qt.Key_Space:
                if not event.isAutoRepeat():
                    for gscene in self.gscenes.itervalues():
                        gscene.set_mode('crossline')

            elif key == Qt.Key_F:

                ##################### Save structure ######################

                # username = self.get_username()
                timestamp = datetime.now().strftime("%m%d%Y%H%M%S")

                # {(name, side): (vol, bbox, edits, id)}
                new_structure_df = self.structure_df_loaded.copy()

                for (name, side), structure_entry in self.structure_volumes.iteritems():
                    struct_id = structure_entry['structure_id']
                    new_structure_df.loc[struct_id]['volume_in_bbox'] = structure_entry['volume_in_bbox']
                    new_structure_df.loc[struct_id]['bbox'] = structure_entry['bbox']
                    new_structure_df.loc[struct_id]['edits'] = structure_entry['edits']

                new_structure_df_fp = DataManager.get_annotation_filepath(stack=self.stack, by_human=False, stack_m='atlasV3',
                                                                       classifier_setting_m=37,
                                                                      classifier_setting_f=37,
                                                                      warp_setting=8, suffix='structures', timestamp=timestamp)
                save_hdf_v2(new_structure_df, new_structure_df_fp)
                self.statusBar().showMessage('3D structure labelings are saved to %s.\n' % new_structure_df_fp)

                # ##################### Save contours #####################

                # self.save()

            # elif key == Qt.Key_A:
            #     print "Reconstructing selected structure volumes..."
            #
            #     curr_structure_label = self.gscenes['sagittal'].active_polygon.properties['label']
            #     curr_structure_side = self.gscenes['sagittal'].active_polygon.properties['side']
            #     self.update_structure_volume(name_u=curr_structure_label, side=curr_structure_side,
            #     use_confirmed_only=False, recompute_from_contours=False, from_gscene_id='sagittal')

            # elif key == Qt.Key_P:
            #     print "Reconstructing all structure volumes..."
            #
            #     structures_curr_section = [(p.properties['label'], p.properties['side'])
            #                                 for p in self.gscenes['sagittal'].drawings[self.gscenes['sagittal'].active_i]]
            #     for curr_structure_label, curr_structure_side in structures_curr_section:
            #         self.update_structure_volume(name_u=curr_structure_label, side=curr_structure_side, use_confirmed_only=False, recompute_from_contours=False)

            elif key == Qt.Key_U:

                # For all structures on the current section
                # structures_curr_section = [(p.properties['label'], p.properties['side'])
                #                             for p in self.gscenes['sagittal'].drawings[self.gscenes['sagittal'].active_i]]
                # for curr_structure_label, curr_structure_side in structures_curr_section:

                curr_structure_label = self.gscenes['sagittal'].active_polygon.properties['label']
                curr_structure_side = self.gscenes['sagittal'].active_polygon.properties['side']

                name_side_tuple = (curr_structure_label, curr_structure_side)
                assert name_side_tuple in self.structure_volumes, \
                "structure_volumes does not have %s. Need to reconstruct this structure first." % str(name_side_tuple)

                if name_side_tuple in self.gscenes['sagittal'].uncertainty_lines:
                    print "Remove uncertainty line"
                    for gscene in self.gscenes.itervalues():
                        gscene.hide_uncertainty_line(name_side_tuple)
                else:
                    print "Add uncertainty line"
                    if curr_structure_side == 'S':
                        name = curr_structure_label
                    else:
                        name = curr_structure_label + '_' + curr_structure_side
                    current_structure_hessians = DataManager.load_confidence(stack_m='atlasV3', stack_f=self.stack, classifier_setting_m=37, classifier_setting_f=37, warp_setting=8,
                    param_suffix=name, what='hessians')
                    H, fmax = current_structure_hessians[84.64]

                    U, S, UT = np.linalg.svd(H)
                    flattest_dir = U[:,-1]

                    current_structure_peakwidth = DataManager.load_confidence(stack_m='atlasV3', stack_f=self.stack, classifier_setting_m=37, classifier_setting_f=37, warp_setting=8,
                    param_suffix=name, what='peak_radius')
                    pw_max_um, _, _ = current_structure_peakwidth[118.75][84.64]
                    len_lossless_res = pw_max_um / XY_PIXEL_DISTANCE_LOSSLESS

                    vol = self.structure_volumes[name_side_tuple]['volume_in_bbox']
                    bbox = self.structure_volumes[name_side_tuple]['bbox']
                    c_vol_res_gl = np.mean(np.where(vol), axis=1)[[1,0,2]] + (bbox[0], bbox[2], bbox[4])

                    e1 = c_vol_res_gl * self.volume_downsample_factor - len_lossless_res * flattest_dir
                    e2 = c_vol_res_gl * self.volume_downsample_factor + len_lossless_res * flattest_dir

                    for gscene in self.gscenes.itervalues():
                        e1_gscene = point3d_to_point2d(e1, gscene)
                        e2_gscene = point3d_to_point2d(e2, gscene)
                        print gscene.id, e1_gscene, e2_gscene
                        gscene.set_uncertainty_line(name_side_tuple, e1_gscene, e2_gscene)

                if name_side_tuple in self.gscenes['sagittal'].structure_onscreen_messages:
                    self.gscenes['sagittal'].hide_structure_onscreen_message(name_side_tuple)
                else:
                    current_structure_zscores = DataManager.load_confidence(stack_m='atlasV3', stack_f=self.stack, classifier_setting_m=37, classifier_setting_f=37, warp_setting=8,
                    param_suffix=name, what='zscores')
                    zscore, fmax, mean, std = current_structure_zscores[118.75]
                    print str((zscore, fmax, mean, std)), np.array(e1_gscene + e2_gscene)/2
                    self.gscenes['sagittal'].set_structure_onscreen_message(name_side_tuple, "zscore = %.2f" % zscore, (e1_gscene + e2_gscene)/2)

        elif event.type() == QEvent.KeyRelease:
            key = event.key()
            if key == Qt.Key_Space:
                if not event.isAutoRepeat():
                    for gscene in self.gscenes.itervalues():
                        gscene.set_mode('idle')

        return False

def point3d_to_point2d(pt3d, gscene):
    """
    Convert a 3D point to 2D point on a gscene.

    Args:
        pt3d ((3,)-ndarray): a point coordinate in lossless-resolution coordinate.
        gscene (QGraphicScene)
    """
    pt3d_gscene_res = pt3d / gscene.data_feeder.downsample
    if gscene.id == 'sagittal' or gscene.id == 'sagittal_tb':
        pt2d = (pt3d_gscene_res[0], pt3d_gscene_res[1])
    elif gscene.id == 'coronal':
        pt2d = (gscene.data_feeder.z_dim - 1 - pt3d_gscene_res[2], pt3d_gscene_res[1])
    elif gscene.id == 'horizontal':
        pt2d = (pt3d_gscene_res[0], gscene.data_feeder.z_dim - 1 - pt3d_gscene_res[2])
    return np.array(pt2d)

def load_structure_names(fn):
    """
    Load structure names from a file.

    Args:
        fn (str): a file containing rows of structure names.
    Returns:
        (list of str)
    """
    names = {}
    with open(fn, 'r') as f:
        for ln in f.readlines():
            abbr, fullname = ln.split('\t')
            names[abbr] = fullname.strip()
    return names


if __name__ == "__main__":

    import argparse
    import sys
    import time

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Launch brain labeling GUI.')

    parser.add_argument("stack_name", type=str, help="stack name")
    parser.add_argument("-f", "--first_sec", type=int, help="first section")
    parser.add_argument("-l", "--last_sec", type=int, help="last section")
    parser.add_argument("-v", "--img_version", type=str, help="image version", default='jpeg')
    parser.add_argument("-d", "--downsample", type=float, help="downsample", default=1)
    parser.add_argument("-p", "--prep", type=int, help="preprocessing id", default=2)
    args = parser.parse_args()

    from sys import argv, exit
    appl = QApplication(argv)

    stack = args.stack_name
    downsample = args.downsample
    img_version = args.img_version
    prep_id = args.prep

    if prep_id == 3:
        default_first_sec, default_last_sec = DataManager.load_cropbox_thalamus(stack)[4:]
    elif prep_id == 2:
        default_first_sec, default_last_sec = DataManager.load_cropbox(stack)[4:]
    else:
        raise

    first_sec = default_first_sec if args.first_sec is None else args.first_sec
    last_sec = default_last_sec if args.last_sec is None else args.last_sec

    m = BrainLabelingGUI(stack=stack, first_sec=first_sec, last_sec=last_sec, downsample=downsample, img_version=img_version, prep_id=prep_id)

    m.showMaximized()
    m.raise_()
    exit(appl.exec_())
