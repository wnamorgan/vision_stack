import platform
import time
import logging
from pathlib import Path
from ultralytics import YOLO

IMG_SIZE    = 640
DEVICE      = 0
FP16        = False
USE_ENGINE  = True


log = logging.getLogger("dnn")


def create_engine(model_path, engine_path, device: int = 0, imgsz: int = 640):
    """
    Export a YOLO model to TensorRT engine if it does not already exist.
    Deletes the intermediate ONNX file and appends _FP16 or _FP32 to the engine file.
    """
    model_path = Path(model_path).resolve()
    engine_path = Path(engine_path).resolve()

    if engine_path.exists():
        log.info("[create_engine] Engine '%s' already exists, skipping export.", engine_path)
        return

    log.info("[create_engine] Engine '%s' not found. Exporting TensorRT engine...", engine_path)
    model = YOLO(str(model_path))

    # Export to TensorRT engine
    model.export(
        format="engine",
        device=device,
        half=FP16,  # Use FP16 if flag is True
        imgsz=imgsz,
    )


    generated_engine = model_path.with_suffix(".engine")
    if generated_engine.exists() and generated_engine != engine_path:
        generated_engine.replace(engine_path)
        log.info("[create_engine] Renamed engine to %s", engine_path)
    elif engine_path.exists():
        log.info("[create_engine] Engine already at %s", engine_path)
    else:
        # Best-effort: find any engine with the model stem prefix
        candidates = sorted(model_path.parent.glob(f"{model_path.stem}*.engine"))
        if candidates:
            candidates[0].replace(engine_path)
            log.info("[create_engine] Renamed engine to %s", engine_path)
        else:
            log.warning("[create_engine] No engine file found to rename.")

    # Delete the intermediate ONNX file if it exists
    onnx_path = model_path.with_suffix(".onnx")
    if onnx_path.exists():
        onnx_path.unlink()  # Delete the ONNX file
        log.info("[create_engine] Deleted intermediate ONNX file: %s", onnx_path)

    log.info("[create_engine] Export complete. Engine saved as: %s", engine_path)


def describe_model(model):
    # Check if the model is a TensorRT engine or a PyTorch model
    if hasattr(model, 'model') and hasattr(model.model, 'args'):
        # For PyTorch models
        precision = "FP16" if model.model.args.get('half', False) else "FP32"
        log.info("Model type: PyTorch | Precision: %s", precision)
    else:
        # For TensorRT engines
        precision = "FP16" if "_FP16" in model.__str__() else "FP32"
        log.info("Model type: TensorRT | Precision: %s", precision)

def get_model(model_path):
    """
    On Jetson (aarch64): ensure TensorRT engine exists and load it.
    On x86: load the PyTorch .pt model directly.
    """
    model_path = Path(model_path).resolve()
    
    # Strip any existing precision suffix from the model name (i.e., _FP16 or _FP32)
    model_name = model_path.stem  # Base name without suffix
    engine_path_fp16 = model_path.with_name(f"{model_name}_FP16.engine")
    engine_path_fp32 = model_path.with_name(f"{model_name}_FP32.engine")

    is_jetson = (platform.machine() == "aarch64")

    if is_jetson and USE_ENGINE:
        # Check for the correct engine based on FP16 flag
        if FP16 and engine_path_fp16.exists():
            log.info("[get_model] Loading TensorRT engine (FP16) from '%s'...", engine_path_fp16)
            model = YOLO(str(engine_path_fp16))
        elif not FP16 and engine_path_fp32.exists():
            log.info("[get_model] Loading TensorRT engine (FP32) from '%s'...", engine_path_fp32)
            model = YOLO(str(engine_path_fp32))
        else:
            # Engine doesn't exist, create one
            log.info(
                "[get_model] Engine not found. Creating TensorRT engine with %s precision...",
                "FP16" if FP16 else "FP32",
            )
            create_engine(model_path, engine_path_fp16 if FP16 else engine_path_fp32, device=DEVICE, imgsz=IMG_SIZE)
            model = YOLO(str(engine_path_fp16 if FP16 else engine_path_fp32))

    else:
        log.info("[get_model] Loading PyTorch model from '%s'...", model_path)
        model = YOLO(str(model_path))

    # Describe the model after loading
    describe_model(model)

    return model
