"""Top level Brain class.

UiInit: initialize the graphical interface
UiElements: interactions between graphical elements and deep functions
base: initialize all Brain objects (MNI, sources, connectivity...)
and associated transformations
BrainUserMethods: initialize functions for user interaction.
"""
import logging
import itertools
import serial 
import sys
import time

import vispy.scene.cameras as viscam
from vispy.scene.visuals import Text
from vispy import app

from .interface import UiInit, UiElements, EngramShortcuts
from .visuals import Visuals
from .cbar import EngramCbar
from .user import EngramUserMethods
from visbrain._pyqt_module import _PyQtModule
from visbrain.config import PROFILER, CONFIG

from ...envs import position_slicer

import numpy as np

logger = logging.getLogger('visbrain')


class Engram(_PyQtModule, UiInit, UiElements, Visuals, EngramCbar,
            EngramUserMethods):
    """Visualization of data on a standard MNI brain.

    By default the Engram module display a standard MNI brain. Then, this brain
    can interact with several objects :

        * Brain (:class:`visbrain.objects.BrainObj`)
        * Sources (:class:`visbrain.objects.SourceObj`)
        * Connectivity (:class:`visbrain.objects.ConnectObj`)
        * Time-series (:class:`visbrain.objects.TimeSeries3DObj`)
        * Pictures (:class:`visbrain.objects.Picture3DObj`)
        * Vectors (:class:`visbrain.objects.VectorObj`)
        * Volume (:class:`visbrain.objects.VolumeObj`)
        * Cross-sections (:class:`visbrain.objects.CrossSecObj`)
        * Region Of Interest (:class:`visbrain.objects.RoiObj`)

    Alternatively, if an other structural template is needed, a brain object
    (BrainObj) can also be used (see brain_obj). CHANGE FOR DOMAIN-AGNOSTIC STRUCTURE

    Parameters
    ----------
    brain_obj : :class:`visbrain.objects.BrainObj` | None
        A brain object.
    vol_obj : :class:`visbrain.objects.VolumeObj` | None
        A volume object.
    cross_sec_obj : :class:`visbrain.objects.CrossSecObj` | None
        A cross-sections object.
    roi_obj : :class:`visbrain.objects.RoiObj` | None
        A Region Of Interest (ROI) object.
    source_obj : :class:`visbrain.objects.SourceObj` | None
        An object (or list of objects) of type source.
    connect_obj : :class:`visbrain.objects.ConnectObj` | None
        An object (or list of objects) of type connectivity.
    time_series_obj : :class:`visbrain.objects.TimeSeries3DObj` | None
        An object (or list of objects) of type time-series.
    picture_obj : :class:`visbrain.objects.Picture3DObj` | None
        An object (or list of objects) of type pictures.
    vector_obj : :class:`visbrain.objects.VectorObj` | None
        An object (or list of objects) of type vector.
    project_radius : float | 10.
        The projection radius to use.
    project_type : {'activity', 'repartition'}
        Define the projection type. Use 'activity' to project the source's
        activity or 'repartition' to get the number of contributing sources per
        vertex.
    project_contribute : bool | False
        Specify if source's can contribute to both hemisphere during projection
        (True) or if it can only be projected on the hemisphere the source
        belong.
    project_mask_color : string/tuple/array_like | 'orange'
        The color to assign to vertex for masked sources.
    project_cmap : string | 'viridis'
        The colormap to use for the source projection.
    project_clim : tuple | (0., 1.)
        Colorbar limits of the projection.
    project_vmin : float | None
        Minimum threshold for the projection colorbar.
    project_under : string/tuple/array_like | 'gray'
        Color to use for values under project_vmin.
    project_vmax : float | None
        Maximum threshold for the projection colorbar.
    project_over : string/tuple/array_like | 'red'
        Color to use for values over project_vmax.
    bgcolor : string/tuple | 'black'
        Background color of the GUI.
    metadata: dictionary
        Dictionary of data information
    rotation: float | 0.
        Amount to iterate the rotation
    carousel_choice: list | [0,2]
        Combinatorial carousel of display options. 0th index denotes how many. 1st index denotes which one.
    carousel_metadata: dictionary 
        Information about how to display the source organization
    control_method: str
        How you would like to control the visualization. Default is keyboard
    """

    def __init__(self, bgcolor='black', verbose=None, **kwargs):
        """Init."""
        # ====================== PyQt creation ======================
        _PyQtModule.__init__(self, verbose=verbose, to_describe='view.wc',
                             icon='brain_icon.svg')
        self._userobj = {}
        self._gl_scale = 100.  # fix appearance for small meshes
        self._camera = viscam.TurntableCamera(name='MainEngramCamera')

        # ====================== Canvas creation ======================
        UiInit.__init__(self, bgcolor)  # GUI creation + canvas
        PROFILER("Canvas creation")

        # ====================== App creation ======================
        PROFILER("Visual elements", as_type='title')
        Visuals.__init__(self, self.view.wc, **kwargs)

        
        # ====================== Metadata Storage ======================
        if 'metadata' in kwargs.keys():
            self.metadata = kwargs['metadata']
        else:
            self.metadata = {}


        # ====================== Rotation Kinetics ======================
        if 'rotation' in kwargs.keys():
            self.rotation = kwargs['rotation']
        else:
            self.rotation = 0


        # ====================== Carousel Options ======================
        self.ease_xyz = False # Between carousel options
        self.ignore_streams = True
        
        if 'carousel_metadata' in kwargs.keys():  
            self.carousel_metadata = kwargs['carousel_metadata']
        else:
            self.carousel_metadata = {}

        # Carousel Display Method
        if 'carousel_display_method' in kwargs.keys():    
            self._carousel_display_method = kwargs['carousel_display_method']
        else:
            self._carousel_display_method = 'text'
    
        # Carousel Options
        if 'hierarchy_lookup' in self.carousel_metadata:
            options = np.asarray(self.carousel_metadata['hierarchy_lookup'])

            self._carousel_options_inds = [np.asarray([0])]

            for dims in (range(len(options))):

                _combs = itertools.combinations(range(len(options)), dims+1)
                _combs = list(_combs)

                for ll,comb in enumerate(_combs):
                    comb = list(comb)
                    if len(comb) > 1:
                        if ll == 0:
                            combs = [np.array(list(comb))+1]
                        else:
                            combs.append(np.array(list(comb))+1)
                    else:
                        if ll == 0:
                            combs = [np.array([comb[0]+1])]
                        else:
                            combs.append(np.array([list(comb)[0]+ 1]))

                self._carousel_options_inds.append(combs)
            
            self._carousel_options_inds[0] = [self._carousel_options_inds[0]]
        
            options = list(options)
            new_options = [np.asarray(['None'])]
            for ii in np.arange(len(options))+1:
                new_options.append(options[ii-1])
            self._carousel_options = np.asarray(new_options)

        else:
            self._carousel_options_inds = [np.asarray([])]

            self._carousel_options = np.asarray(['None'])

        # Carousel Choice
        if 'carousel_choice' in kwargs.keys():
            self._carousel_choice = kwargs['carousel_choice']
            self._prev_carousel_choice = kwargs['carousel_choice']
        else:
            self._carousel_choice = [0,0]
            self._prev_carousel_choice = [0,0]

        # Display Method
        self.update_carousel()


        # Toggle Options
        self._userdistance = [0]
        self._uservelocity = 0

        # ====================== Control Device ======================
        if 'control_method' in kwargs.keys():
            self.control_method = kwargs['control_method']
        else:
            self.control_method = 'keyboard'

        if self.control_method is 'IR_Distance':
            self.ser = serial.Serial('/dev/cu.usbmodem144101')
            self.use_distance = True
        else:
            self.ser = None


        self.prev_rotation = 0

        def arduino_control(method='none'):
            if self.ser is not None:
                # Check Arduino inputs
                try:
                    b = self.ser.readline()         # read a byte string
                    string_n = b.decode()  # decode byte string into Unicode  
                    message = string_n.rstrip() # remove \n and \r
                    messages = message.split('|')
                    distance = messages[0]
                    command = messages[1]
                except:
                    distance = 500
                    command = 'NONE'


            if method == 'IR_Distance':

                if self.use_distance:
                    THRESHOLD = 20 # cm
                    HEIGHT = 0
                    flt = float(distance)
                    self._userdistance = np.append(self._userdistance,flt) # convert string to float

                    # Distance Selections
                    if flt < HEIGHT+THRESHOLD:
                        self._carousel_choice[0] = 0
                    if flt >= HEIGHT + (THRESHOLD) and flt < HEIGHT+(2*THRESHOLD):
                        self._carousel_choice[0] = 1
                    if flt >= HEIGHT + (2*THRESHOLD):
                        self._carousel_choice[0] = 3
                        
                    
                # Remote Option

                if command != 'NONE':
                    print(command)

                if command == 'POWER':
                    sys.exit()

                if command == 'ST/REPT' and not self.use_distance:
                    if self._carousel_choice[0] < (len(self._carousel_options_inds)-1):
                        if self._carousel_choice[0] == 1:
                            self._carousel_choice[0] = 3
                        else:
                            self._carousel_choice[0] += 1
                    else:
                        self._carousel_choice[0] = 0
                    self._carousel_choice[1] = 0
                
                if command == 'EQ':
                    if self.use_distance:
                        self.use_distance = False
                    else:
                        self.use_distance = True

                if command == 'FUNC/STOP':
                    if self._carousel_choice[1] < (len(self._carousel_options_inds[self._carousel_choice[0]])-1):
                        self._carousel_choice[1] += 1
                    else:
                        self._carousel_choice[1] = 0
                
                if command == 'VOL+' or command == 'VOL-':
                    if command == 'VOL+':
                        self.view.wc.camera.distance -= 5000
                    else: 
                        self.view.wc.camera.distance += 5000

                if command == 'UP':
                    self.rotation += .25

                elif command == 'DOWN':
                    self.rotation -= .25

                elif command == 'FAST BACK':
                    if np.sign(self.timescaling) == 1:
                        self.timescaling = -0.1
                    else:
                        self.timescaling -= 0.10

                elif command == 'FAST FORWARD':
                    if np.sign(self.timescaling) == -1:
                        self.timescaling = 0.1
                    else:
                        self.timescaling += 0.10

                elif command == 'PAUSE':
                    if self.timescaling == 0:
                        print('PLAY')
                        self.timescaling = self.default_timescaling
                        self.rotation = self.prev_rotation
                        self.displayed_time = self.time_cache
                        self.time_cache = None

                    else:
                        print('PAUSE')
                        self.prev_rotation = self.rotation
                        self.time_cache = self.displayed_time
                        self.rotation = 0
                        self.timescaling = 0
                        self.paused = True

                if self.paused == True:
                    if command == 'FAST FORWARD':
                        self.time_cache += .02
                    elif command == 'FAST BACK':
                        self.time_cache -= .02


                # Remote Numbers
                if command == '0':
                    self.view.wc.camera.azimuth = 0 
                    self.view.wc.camera.elevation = 90

                elif command == '1':
                    self.view.wc.camera.azimuth = 0
                    self.view.wc.camera.elevation = -90

                elif command == '2':
                    self.view.wc.camera.azimuth = 90 
                    self.view.wc.camera.elevation = 0

                elif command == '3':
                    self.view.wc.camera.azimuth = -90 
                    self.view.wc.camera.elevation = 0

                elif command == '4':
                    self.view.wc.camera.azimuth = 0 
                    self.view.wc.camera.elevation = 0

                elif command == '5':
                    self.view.wc.camera.azimuth = 180 
                    self.view.wc.camera.elevation = 0

                elif command == '6':
                    self.view.wc.camera.azimuth = 45 
                    self.view.wc.camera.elevation = 30

                elif command == '7':
                    self.view.wc.camera.azimuth = 45 
                    self.view.wc.camera.elevation = -30

                elif command == '8':
                    self.view.wc.camera.azimuth = -45 
                    self.view.wc.camera.elevation = 30

                elif command == '9':
                    self.view.wc.camera.azimuth = -45 
                    self.view.wc.camera.elevation = -30

        
        # ====================== Timer Creation ======================

        self.loop_shift = 0
        self.start_offset = 0
        self.default_timescaling = 1/4
        self.timescaling = self.default_timescaling
        self.time_cache = None
        self.displayed_time = 0

        self.paused = False

        def on_timer(*args, **kwargs): 

            # Change Source Radii and Connectivity Values
            if self.time_cache is None:
                time_inc = (args[0].dt*self.timescaling)
                self.displayed_time = self.loop_shift+(self.displayed_time + time_inc)%((np.shape(self.sources[0].data)[1]/self.metadata['fs'])-self.loop_shift)
            else:
                self.displayed_time = self.loop_shift+(self.time_cache)%((np.shape(self.sources[0].data)[1]/self.metadata['fs'])-self.loop_shift)
            
            timepoint = int(self.displayed_time*self.metadata['fs'])
            for source in self.sources:
                source._update_radius(timepoint=timepoint)
            for connect in self.connect:
                connect._update_time(timepoint=timepoint)

            arduino_control(self.control_method)

            self.update_target_positions()
            self.update_carousel()
            self.update_visibility()
            self._prev_carousel_choice = self._carousel_choice

            if len(self._userdistance) > 2:
                self._userdistance = [-1]

            # Update Time Display
            t_str = str(round(self.displayed_time, 3)) + ' s'
            if not hasattr(self, '_time'):
                self._time = Text(t_str, parent=self.view.canvas.scene, color='white')
            else:
                self._time.text = t_str
            self._time.anchors = ('right','bottom')
            self._time.font_size = self.view.canvas.size[1] // 200
            self._time.pos = (49)*self.view.canvas.size[0] // 50, (19)*self.view.canvas.size[1] // 20
            self._time.update()

            # Ease to New Positions if Triggered
            if self.ease_xyz:
                self.ease_xyz = False
                for source in self.sources:
                    out = source._ease_to_target_position()
                    if out:
                        self.ease_xyz = True
                for connect in self.connect:
                    out = connect._ease_to_target_position()
                    if out:
                        self.ease_xyz = True
            
            # if hasattr(self.view.wc, 'camera'):
            #     diff_az = self.target_azimuth - self.view.wc.camera.azimuth
            #     diff_el = self.target_elevation - self.view.wc.camera.elevation

            #     # Ease scene rotation
            #     if (diff_az != 0.) | (diff_el != 0.):

            #         # Flip target and current (since I cannot find a way to update the shortcuts directly)
            #         if self.first_ease:
            #             temp_ = self.target_elevation
            #             self.target_elevation = self.view.wc.camera.elevation
            #             self.view.wc.camera.elevation = temp_
            #             temp_ = self.target_azimuth
            #             self.target_azimuth = self.view.wc.camera.azimuth 
            #             self.view.wc.camera.azimuth = temp_

            #             self.first_ease = False

            #         if (abs(diff_az) > 0.001) | (abs(diff_el) > 0.001):
            #              self.view.wc.camera.azimuth += .1*(diff_az)
            #              self.view.wc.camera.elevation += .1*(diff_el)
            #              print('updating rotation')
            #              if self.first_ease:
            #                 self.first_ease = False
            #         else:
            #             self.view.wc.camera.azimuth = self.target_azimuth 
            #             self.view.wc.camera.elevation = self.target_elevation
            #             self.first_ease = True
                
                #Iterate scene rotation
                # else:
            self.view.wc.camera.azimuth += self.rotation

            self.view.wc.canvas.update()

        kw = dict(connect=on_timer, app=CONFIG['VISPY_APP'],
                  interval='auto', iterations=-1)
        self._app_timer = app.Timer(**kw)
        self._app_timer.start()

        # ====================== Ui interactions ======================
        UiElements.__init__(self)  # GUI interactions
        PROFILER("Ui interactions")
        self._shpopup.set_shortcuts(self.sh)  # shortcuts dict

        # ====================== Cameras ======================
        # Main camera :
        self.view.wc.camera = self._camera
        self._vbNode.parent = self.view.wc.scene
        self.atlas.camera = self._camera
        self.roi.camera = self._camera
        self.atlas._csize = self.view.canvas.size
        self.atlas.rotate('top')
        self.atlas.camera.set_default_state()
        PROFILER("Cameras creation")

        # Set easing
        self.target_azimuth = self.view.wc.camera.azimuth
        self.target_elevation = self.view.wc.camera.elevation
        self.first_ease = True

        # ====================== Colorbar ======================
        camera = viscam.PanZoomCamera(rect=(-.2, -2.5, 1, 5))
        EngramCbar.__init__(self, camera)
        PROFILER("Colorbar and panzoom creation")
        self.background_color(bgcolor)

        # ====================== Shortcuts ======================
        EngramShortcuts.__init__(self, self.cbqt.cbviz._canvas)
        PROFILER("Set engram shortcuts")

        self._fcn_on_load()
        PROFILER("Functions on load")

    def _fcn_on_load(self):
        """Function that need to be executed on load."""
        # Setting panel :
        self._objsPage.setCurrentIndex(0)
        self.menuDispQuickSettings.setChecked(True)
        self._source_tab.setCurrentIndex(0)
        self._obj_type_lst.setCurrentIndex(0)
        # Progress bar and rotation panel :
        self.progressBar.hide()
        self.userRotationPanel.setVisible(False)
        # Display menu :
        self.menuDispEngram.setChecked(self.atlas.mesh.visible)
        # Objects :
        self._fcn_obj_type()
        # Colorbar :
        self._fcn_menu_disp_cbar()

    def update_target_positions(self):
        n_choices = self._carousel_choice[0]
        which_choice = self._carousel_choice[1]
        choice = self._carousel_options_inds[n_choices][which_choice] - 1 # Shift to Account for "None"

        if self._carousel_choice[0] == 2 or self._carousel_choice[0] == 3:
            self.ignore_streams = False
        else:
            self.ignore_streams = True
        
        xyz = position_slicer(self.carousel_metadata,method=choice,ignore_streams=self.ignore_streams)
        for source in self.sources:
            source._update_target_position(xyz=xyz)
        for connect in self.connect:
            connect._update_target_position(nodes=xyz)

        self.ease_xyz = True

    def update_visibility(self):
        if self._carousel_choice[0] != 3:
            self.engram_control(visible=False)
        else:
            self.engram_control(visible=True)
    
    def update_carousel(self):

        if self._carousel_display_method == 'text':

            # Initialize
            if not hasattr(self,'_labels'):
                self._labels = [Text('', parent=self.view.canvas.scene, color='white')]
                for count in range(len(self._carousel_options_inds)-2):
                    self._labels.append(Text('', parent=self.view.canvas.scene, color='white'))

            n_choices = self._carousel_choice[0]
            which_choice = self._carousel_choice[1]
            choice = self._carousel_options_inds[n_choices][which_choice]
            label_choice = self._carousel_options[choice]
            if len(label_choice) != n_choices:
                label_choice = [label_choice]
            for ii,val in enumerate(label_choice):
                if hasattr(val,'size'):
                    for jj, string in enumerate(val):
                        if jj == 0:
                            full_string = string
                        else:
                            full_string = full_string + ' | ' + string
                else:
                    full_string = val

                self._labels[ii].text = full_string
                self._labels[ii].anchors = ('left','bottom')
                self._labels[ii].font_size = self.view.canvas.size[1] // 200
                self._labels[ii].pos = self.view.canvas.size[0] // 50, (19-ii)*self.view.canvas.size[1] // 20
                self._labels[ii].update()
            
            for jj in np.arange(len(self._labels)-(ii+1))+(ii+1):
                self._labels[jj].text = ''
                self._labels[jj].update()

        else:
            print('No carousel displayed')