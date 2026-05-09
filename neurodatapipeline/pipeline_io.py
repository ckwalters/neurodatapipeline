import os
import shutil
import logging
from pythonjsonlogger import jsonlogger
from pathlib import Path
from .config import *

def find_file(dir: Path, key: str="", is_dir=False, retsingle=True, verbose=False):
    """Find file or directory in dir with key in name."""
    if is_dir:
        paths = [d for d in dir.iterdir() if key in d.name and d.is_dir()]
    else:
        paths = [p for p in dir.iterdir() if key in p.name]
    
    if len(paths)==0:
        return
    elif len(paths)==1:
        return paths[0]
    elif len(paths)>1 and retsingle:
        if verbose:
            print(f"{dir.name} -- More than one {key} path found, taking latest.")
        return paths[-1]
    else:
        return paths

def check_make_dir(path: Path):
    """Makes directory if it doesn't already exist."""
    if not path.exists():
        os.mkdir(path)

def check_disk_space(root: Path=SESSIONS_PATH, threshold_gB=500):
    _, _, free = shutil.disk_usage(root)
    if free < (threshold_gB*1000000000):
        return False
    else:
        return True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt=r"%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH)
    ]
)

def make_json_logger():
    logger = logging.getLogger("pipeline_logger")
    logger.setLevel(logging.DEBUG)  # will accept debug and above

    file_handler = logging.FileHandler(LOG_PATH)
    file_handler.setLevel(logging.INFO)  # only write info and above

    format = "{asctime}{session}{code}{message}"
    formatter = jsonlogger.JsonFormatter(format, style="{")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.propagate = False
    
    return logger

logger = make_json_logger()

def log(message: str, p="NDPIPELINE", r=None, c=None, n=None, w=False):
    # Print message
    display_str = f"{p} -- {message}"
    if c is not None:
        display_str = display_str + f" -- code {c}"
    if p!="NDPIPELINE":
        display_str = "    " + display_str
    print(display_str)

    # Write to log file
    if w and GLOBAL_WRITE:
        logger.info({
            "parent": p,
            "child": r,
            "node": n,
            "code": c,
            "message": message,
        })