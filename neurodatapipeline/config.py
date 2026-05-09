from pathlib import Path

## Pipeline
# Program paths
CATGT_PATH = Path("...\\CatGT-win")
TPRIME_PATH = Path("...\\TPrime-win")
PIPELINE_PATH = Path(__file__).resolve()

# Conda env names
KS_ENV = "ks4"
SI_ENV = "si"

# Organized and processed data path
SESSIONS_PATH = Path("") # Session-based data

# Session-level folder datetime pattern
SESSION_DT_PATTERN = r"%Y-%m-%d_%H-%M-%S"

# Pipeline logging
STATES_PATH = SESSIONS_PATH / "session_states.json"
LOG_PATH = "sortinglib/pipeline_log.json"
GLOBAL_WRITE = True


## Organize raw data
# Subject ID regex; set to None if no subject IDs used
SUBJECT_ID_PATTERN = r"Subject"+r"\d{2}"

# SpikeGLX data
SGLXDATA_PATH = Path("")

# Behavior (text/csv) path
BEHAVIOR_PATH = Path("")

# Video path
VIDEO_PATH = Path("")

# Behavior and video datetime patterns
BEHAVIOR_PATTERNS = {
    "behavior": {
        "dt_format": r"%Y%m%d%H%M%S",
        "dt_regex": "\d{13}",
    },
    "video": {
        "dt_format": r"%Y-%m-%d_%H-%M-%S",
        "dt_regex": "\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}",
    }
}