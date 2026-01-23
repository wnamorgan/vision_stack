import numpy as np
import cv2


def RGB_image_from_frame(frame, pixel_format):
    data = frame.get_data()
    width = frame.get_width()
    height = frame.get_height()

    # Dictionary to map pixel formats to numpy dtype and reshape
    format_mapping = {
        'Mono8':           (np.uint8, (height, width)),
        'Mono16':          (np.uint16, (height, width)),
        'RGB8Packed':      (np.uint8, (height, width, 3)),
        'BayerRG8':        (np.uint8, (height, width)),
        'BayerRG16':       (np.uint16, (height, width)),
        'Mono10Packed':    (np.uint16, (height, width)),
        'BayerRG10Packed': (np.uint16, (height, width)),
        'Mono12Packed':    (np.uint16, (height, width)),
        'BayerRG12Packed': (np.uint16, (height, width)),
        'YUV411Packed':    (np.uint8, (height, width, 3)),  # Needs conversion
        'YUV422Packed':    (np.uint8, (height, width, 2)),  # Needs conversion
        'YUV444Packed':    (np.uint8, (height, width, 3)),  # Needs conversion
        'Mono10p':         (np.uint16, (height, width)),
        'BayerRG10p':      (np.uint16, (height, width)),
        'Mono12p':         (np.uint16, (height, width)),
        'BayerRG12p':      (np.uint16, (height, width)),
        'YCbCr8':          (np.uint8, (height, width, 3)),  # Needs conversion
        'YCbCr422_8':      (np.uint8, (height, width, 2)),  # Needs conversion
        'YCbCr411_8':      (np.uint8, (height, width, 3)),  # Needs conversion
        'BGR8':            (np.uint8, (height, width, 3)),  # BGR to RGB conversion
        'BGRa8':           (np.uint8, (height, width, 4))   # BGRA to RGB conversion
    }

    if pixel_format not in format_mapping:
        raise ValueError(f"Unsupported pixel format: {pixel_format}")

    dtype, shape = format_mapping[pixel_format]

    # Convert image data to numpy array
    image = np.frombuffer(data, dtype=dtype).reshape(shape)

    return convert_image_to_rgb(image,pixel_format)

def convert_image_to_rgb(image,pixel_format):

    # Handle specific formats needing conversion
    if pixel_format in ['YUV411Packed', 'YUV422Packed', 'YUV444Packed']:
        image = convert_yuv_to_rgb(image)
    elif pixel_format in ['YCbCr8', 'YCbCr422_8', 'YCbCr411_8']:
        image = convert_ycbcr_to_rgb(image)
    elif pixel_format == 'BGR8':
        image = image[:, :, ::-1]  # Convert BGR to RGB
    elif pixel_format == 'BGRa8':
        image = image[:, :, :3]  # Remove alpha channel
        image = image[:, :, ::-1]  # Convert BGR to RGB
    elif pixel_format == 'BayerRG8':
        image = convert_RG8_to_RGB(image)

    return image


def convert_yuv_to_rgb(yuv_image):
    # Implement YUV to RGB conversion
    return yuv_image

def convert_ycbcr_to_rgb(ycbcr_image):
    # Implement YCbCr to RGB conversion
    return ycbcr_image

def convert_RG8_to_RGB(RG8_image):
    return cv2.cvtColor(RG8_image, cv2.COLOR_BayerRG2RGB)
    
# Something is wrong here; the camera is currently producing BayerRG8, but the conversion 
# using COLOR_BayerRG2RGB yields a BGR, likely implying the actual format is BayerBG8
def frame_to_bgr(cam,frame):
    image = cam.array_from_buffer_address(frame)
    #print("shape: ", image.shape)
    bgr_image = image
    if not 0 in image.shape:
        pixel_format = cam.cam.get_pixel_format_as_string()
        bgr_image = convert_image_to_rgb(image, pixel_format)
    return bgr_image    

def frame_to_BayerBG8(cam,frame):
    # Currently assumes camera already returns a Bayer BG8; bad assumption in general, but with
    # this function, at least it only occurs here; expand functionality as needed
    return cam.array_from_buffer_address(frame)