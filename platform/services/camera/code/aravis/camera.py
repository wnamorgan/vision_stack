import numpy as np
import cv2
import gi
import ctypes
from code.aravis.utils.aravis_interface import get_feature

gi.require_version ('Aravis', '0.8')
from gi.repository import Aravis

Aravis.debug_enable('all')
Aravis.enable_interface("USB3Vision")
Aravis.disable_interface("GigEVision")
class AravisException(Exception):
    pass
class Camera():
    def __init__(self,cam_args):
        self.name = None
        try:
            self.cam = Aravis.Camera.new (None)
        except TypeError:
            print ("No camera found")
            exit ()

        self.name   = get_feature(self.cam,"DeviceModelName")
        self.SensorWidth  = get_feature(self.cam,"SensorWidth") 
        self.SensorHeight = get_feature(self.cam,"SensorHeight")

        self.enable_chunk_data(['Timestamp','OffsetX','OffsetY','Width','Height','Gain','ExposureTime'])

        self.process_args(cam_args)

        self.dev    = self.cam.get_device()
        self.stream = self.cam.create_stream()
        #self.cam.set_feature("ChunkModeActive", True)
        
        self.chunk_parser = self.cam.create_chunk_parser()
        if self.stream is None:
            raise AravisException("Error creating buffer")
        self._frame = None
        self._last_payload = 0 
        self._available_buffers = 0
        self._allocated_buffers = 0
        self.sw_trigger = False

    def process_args(self, cam_args):
        (Width,Height) = (2000,2000) 
        #(Width,Height) = (2856,2848)
        OffsetX=(self.SensorWidth-Width)/2
        OffsetY=(self.SensorHeight-Height)/2
        if 'set_region' in cam_args:
            ROI = cam_args['set_region']
            try:
                (OffsetX,OffsetY,Width,Height) = (ROI[0],ROI[1],ROI[2],ROI[3])
            except:
                print("User defined ROI invalid")
        self.limit_ROI(OffsetX,OffsetY,Width,Height)   
        self.cam.set_region(self.OffsetX,self.OffsetY,self.Width,self.Height) 

        if 'AcquisitionFrameRate' in cam_args:
            frame_rate_bounds = self.cam.get_frame_rate_bounds()
            print("Old Camera FPS:           ", self.cam.get_frame_rate())
            print("Camera FR Bounds:     ", self.cam.get_frame_rate_bounds())    
            print("Frame Rate Available: ", self.cam.is_frame_rate_available())
            self.cam.set_frame_rate_enable(True)
            new_frame_rate = np.floor(min(max(cam_args['AcquisitionFrameRate'], frame_rate_bounds[0]), frame_rate_bounds[1]))
            self.cam.set_float('AcquisitionFrameRate', new_frame_rate)
            print("New Camera FPS:           ", self.cam.get_frame_rate())

        if 'exposure_time_ms' in cam_args:
            print("Old Exposure Time:       ", self.cam.get_exposure_time())
            self.cam.set_string('ExposureAuto', 'Off')
            self.cam.set_exposure_time(cam_args['exposure_time_ms']*1000) # us
            print("New Exposure Time:       ", self.cam.get_exposure_time())            
        
    def limit_ROI(self,OffsetX,OffsetY,Width,Height):
        N=8
        # Make sure the ROI fits
        Width   = min(Width,self.SensorWidth)
        Height  = min(Height,self.SensorHeight)
        OffsetX = min(OffsetX,self.SensorWidth-Width)
        OffsetY = min(OffsetY,self.SensorHeight-Height)
        # Make sure everything is divisible by four
        self.OffsetX = OffsetX - np.mod(OffsetX,N)
        self.OffsetY = OffsetY - np.mod(OffsetY,N)
        self.Width   = Width   - np.mod(Width,  N)
        self.Height  = Height  - np.mod(Height, N)

    def update_ROI(self, ROI):
        self.cam.stop_acquisition()
        self.stream.stop_thread(True)
        self.limit_ROI(ROI[0], ROI[1], ROI[2], ROI[3])
        self.cam.set_region(self.OffsetX,self.OffsetY,self.Width,self.Height) 
        payload = self.cam.get_payload()
        for i in range(self._allocated_buffers):
            self.stream.push_buffer(Aravis.Buffer.new(payload))
        self.stream.start_thread()    
        self.cam.start_acquisition()

    def enable_chunk_data(self,chunk_list):
        if self.cam.are_chunks_available():
            self.cam.set_chunks(', '.join(chunk_list)) 
            #self.cam.set_chunks("Timestamp, Width, Height, Gain")
            if self.cam.get_chunk_mode():
                for chunk in chunk_list:
                    if not self.cam.get_chunk_state(chunk):
                        return False
                    print(chunk," = true")

    def get_feature_type(self, name):
        genicam = self.dev.get_genicam()
        node = genicam.get_node(name)
        if not node:
            raise AravisException("Feature {} does not seem to exist in camera".format(name))
        return node.get_node_name()

    def get_feature(self, name):
        """
        return value of a feature. independantly of its type
        """
        ntype = self.get_feature_type(name)
        if ntype in ("Enumeration", "String", "StringReg"):
            return self.dev.get_string_feature_value(name)
        elif ntype == "Integer":
            return self.dev.get_integer_feature_value(name)
        elif ntype == "Float":
            return self.dev.get_float_feature_value(name)
        elif ntype == "Boolean":
            return self.dev.get_integer_feature_value(name)
        else:
            self.logger.warning("Feature type not implemented: %s", ntype)

    def set_feature(self, name, val):
        """
        set value of a feature
        """
        ntype = self.get_feature_type(name)
        if ntype in ("String", "Enumeration", "StringReg"):
            return self.dev.set_string_feature_value(name, val)
        elif ntype == "Integer":
            return self.dev.set_integer_feature_value(name, int(val))
        elif ntype == "Float":
            return self.dev.set_float_feature_value(name, float(val))
        elif ntype == "Boolean":
            return self.dev.set_integer_feature_value(name, int(val))
        else:
            self.logger.warning("Feature type not implemented: %s", ntype)

    def get_genicam(self):
        """
        return genicam xml from the camera
        """
        return self.dev.get_genicam_xml()

    def get_feature_vals(self, name):
        """
        if feature is an enumeration then return possible values
        """
        ntype = self.get_feature_type(name)
        if ntype == "Enumeration":
            return self.dev.get_available_enumeration_feature_values_as_strings(name)
        else:
            raise AravisException("{} is not an enumeration but a {}".format(name, ntype))

    def stop_acquisition(self):
        self.cam.stop_acquisition()   
        pass     

    def show_frame(frame):
        import cv2
        cv2.imshow("capture", frame)
        cv2.waitKey(0)


    def create_buffers(self, nb=10, payload=None):
        if not payload:
            payload = self.cam.get_payload()
        for _ in range(0, nb):
            self.stream.push_buffer(Aravis.Buffer.new(payload))


    def __str__(self):
        return "Camera: " + self.name

    def __repr__(self):
        return self.__str__()

    def trigger(self):
        """
        trigger camera to take a picture when camera is in software trigger mode
        """
        self.execute_command("TriggerSoftware")

    def start_acquisition(self, nb_buffers=10):
        payload = self.cam.get_payload()
        if payload != self._last_payload:
            #FIXME should clear buffers
            self.create_buffers(nb_buffers, payload) 
            self._last_payload = payload
        self._available_buffers=nb_buffers
        self._allocated_buffers = nb_buffers            
        self.cam.start_acquisition()

    def start_acquisition_trigger(self, nb_buffers=5): # SHOULD BE nb_buffers=1
        self.set_feature("AcquisitionMode", "Continuous") #Not sure why this isn't SingleFrame
        self.set_feature("TriggerSource", "Software") #wait for trigger t acquire image
        self.set_feature("TriggerMode", "On") #Not documented but necesary
        self.start_acquisition(nb_buffers)
        print("Software Trigger")
        self.sw_trigger = True

    def start_acquisition_continuous(self, nb_buffers=15):
        self.set_feature("AcquisitionMode", "Continuous") #no acquisition limits
        self.set_feature("TriggerMode", "Off")
        self.start_acquisition(nb_buffers)    
        print("Continuous Trigger")
    def pop_frame(self, timestamp=False, timeout_s=None):


        # Squeeze trigger to capture image if sw_trigger enabled
        if self.sw_trigger:
            self.cam.software_trigger()

        if self._available_buffers<self._allocated_buffers:
            print("User is not returning buffers; please use push_frame - Expanding buffers for now")
            payload = self.cam.get_payload()
            for _ in range(self._available_buffers, self._allocated_buffers):
                self.stream.push_buffer(Aravis.Buffer.new_allocate(payload))  
            self._available_buffers=self._allocated_buffers          

                
        # Get the buffer
        frame = None
        if timeout_s is not None:
            timeout_us = int(timeout_s * 1_000_000)
            timeout_pop = getattr(self.stream, "timeout_pop_buffer", None)
            try_pop = getattr(self.stream, "try_pop_buffer", None)
            if callable(timeout_pop):
                try:
                    frame = timeout_pop(timeout_us)
                except TypeError:
                    frame = timeout_pop()
            elif callable(try_pop):
                frame = try_pop()
        if frame is None:
            frame = self.stream.pop_buffer()
        if frame:
            self._available_buffers -= 1
            return frame
        else:
            print("No Image")
            return None
 
    def push_frame(self,frame):
        self.stream.push_buffer(frame)
        self._available_buffers += 1

    def get_frame(cam):
        cam.start_acquisition()
        frame = cam.pop_frame()
        cam.stop_acquisition()
        return frame        
    
    def shutdown(self):
        self.cam.stop_acquisition()
        self.stream.stop_thread(True)
        self.stream = None
        self.dev = None
	#Delete the objects on shutdown: socket will be closed!
        del self.stream
        del self.dev
        del self.cam    

    def array_from_buffer_address(self, buf):
        if not buf:
            return None
        pixel_format = buf.get_image_pixel_format()
        bits_per_pixel = pixel_format >> 16 & 0xff
        if bits_per_pixel == 8:
            INTP = ctypes.POINTER(ctypes.c_uint8)
        else:
            INTP = ctypes.POINTER(ctypes.c_uint16)
        addr = buf.get_data()
        ptr = ctypes.cast(addr, INTP)
        im = np.ctypeslib.as_array(ptr, (buf.get_image_height(), buf.get_image_width()))
        im = im.copy()
        return im   
