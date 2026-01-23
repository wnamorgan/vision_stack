import gi

gi.require_version ('Aravis', '0.8')
from gi.repository import Aravis

class AravisException(Exception):
    pass

def get_camera():

    Aravis.enable_interface ("Fake")

    try:
        camera = Aravis.Camera.new (None)
    except TypeError:
        print ("No camera found")
        exit ()

    return camera

def get_feature_type(camera, name):
    device = camera.get_device()
    genicam = device.get_genicam()
    node = genicam.get_node(name)
    if not node:
        raise AravisException("Feature {} does not seem to exist in camera".format(name))
    return node.get_node_name()

def get_feature(camera, name):
    """
    return value of a feature. independantly of its type
    """
    device = camera.get_device()
    ntype = get_feature_type(camera,name)
    if ntype in ("Enumeration", "String", "StringReg"):
        return device.get_string_feature_value(name)
    elif ntype == "Integer":
        return device.get_integer_feature_value(name)
    elif ntype == "Float":
        return device.get_float_feature_value(name)
    elif ntype == "Boolean":
        return device.get_boolean_feature_value(name)
    else:
        raise AravisException("Feature type not implemented: %s", ntype)

def set_feature(camera, name, val):
    """
    set value of a feature
    """
    device = camera.get_device()
    ntype = get_feature_type(camera,name)
    if ntype in ("String", "Enumeration", "StringReg"):
        return device.set_string_feature_value(name, val)
    elif ntype == "Integer":
        return device.set_integer_feature_value(name, int(val))
    elif ntype == "Float":
        return device.set_float_feature_value(name, float(val))
    elif ntype == "Boolean":
        return device.set_boolean_feature_value(name, int(val))
    else:
        raise AravisException("Feature type not implemented: %s", ntype)       
    
def get_feature_modes(cam,feature_name='AcquisitionMode'):
    modes = cam.get_device().get_feature(feature_name).get_entries()
    print(f"{feature_name} Names:  ", [mode.get_name()  for mode in modes])
    print(f"{feature_name} Values: ",[mode.get_value() for mode in modes])
def reset_camera():
    #import gi
    #gi.require_version ('Aravis', '0.8')
    #from gi.repository import Aravis
    camera = Aravis.Camera.new (None)
    camera.execute_command('DeviceReset')
    del camera