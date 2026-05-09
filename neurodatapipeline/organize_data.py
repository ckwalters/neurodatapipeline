import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from .config import *
from .pipeline_io import check_disk_space
from .sglx_metadata import find_meta_path, readMeta


def organize_new_sessions(search_str: str=""):
    """Batch make new session-level directories for raw SGLX data."""
    session_paths = find_sglx_recordings(search_str, source_path=SGLXDATA_PATH)
    for session_path in session_paths:
        if check_disk_space():
            organize_recording_session(session_path)


def organize_existing_sessions(search_str: str=""):
    """For existing session-level directories, check for new behavior data."""
    session_dirs = [d for d in SESSIONS_PATH.iterdir() if d.is_dir() and search_str in d.name]
    for session_dir in session_dirs:
        if check_disk_space():
            maintain_recording_session(session_dir)


def organize_recording_session(sglx_session_path: Path, suppress_data_move=False):
    """
    For a single sglx recording session, create new session-level directory and copy all relevant data.
    Parameters:
        sglx_session_path (Path): raw sglx recording directory or catgt-processed recording directory
        suppress_data_move (bool): can set to True for testing file structure and paths
    """
    
    ## Metadata
    # Find subject name
    if SUBJECT_ID_PATTERN is not None:
        subject_id = re.search(SUBJECT_ID_PATTERN, sglx_session_path.name).group()
    else:
        subject_id = None

    # Check if catgt has been run
    if "catgt" in sglx_session_path.name:
        sglx_session_name = sglx_session_path.name.replace("catgt_","")
        ephys_subdir_name = "ephys_catgt"
    else:
        sglx_session_name = sglx_session_path.name
        ephys_subdir_name = "ephys_sglx"
    
    # SGLX recording start datetime
    first_recording_dir = sglx_session_path / f"{sglx_session_name}_imec0"
    recording_metadata = readMeta(find_meta_path(first_recording_dir))
    if ephys_subdir_name=="ephys_sglx":
        recording_datetime_str = recording_metadata["fileCreateTime"]
    elif ephys_subdir_name=="ephys_catgt":
        recording_datetime_str = recording_metadata["fileCreateTime_original"]
    recording_datetime = datetime.strptime(recording_datetime_str, r"%Y-%m-%dT%H:%M:%S")

    # Make session-level dir
    session_dir_name = f"{recording_datetime.strftime(SESSION_DT_PATTERN)}"
    if SUBJECT_ID_PATTERN is not None:
        session_dir_name = f"{subject_id}_{session_dir_name}"
    session_dir = get_session_subdir(SESSIONS_PATH / session_dir_name)

    print(f"{session_dir_name} -- Created session.")

    ## Ephys data
    import_sglx_data(session_dir, sglx_session_path, suppress_data_move=suppress_data_move)

    ## Behavior data
    import_behavior_data(session_dir, recording_datetime, subject_id, suppress_data_move=suppress_data_move)

    ## Video data
    import_video_data(session_dir, recording_datetime, subject_id, suppress_data_move=suppress_data_move)


def maintain_recording_session(session_dir: Path, behavior_source=BEHAVIOR_PATH, video_source=VIDEO_PATH,
                               suppress_data_move=False):
    """Given a recording session dir, check for any new behavior or video data to import."""

    # Metadata
    session_name = session_dir.name
    subject_id = session_name.split("_")[0]
    rec_datetime = datetime.strptime("_".join(session_name.split("_")[1:]), SESSION_DT_PATTERN)

    ## Behavior data
    if behavior_source is not None:
        import_behavior_data(session_dir, subject_id, rec_datetime, source_path=behavior_source, suppress_data_move=suppress_data_move)

    ## Video data
    if video_source is not None:
        import_video_data(session_dir, subject_id, rec_datetime, source_path=video_source, suppress_data_move=suppress_data_move)


def import_sglx_data(session_dir: Path, sglx_session_path: Path, suppress_data_move=False):
    """
    Moves SGLX data to session directory.
    Parameters:
        session_dir (Path): session-level directory path
        sglx_session_path (Path): path of raw/catgt sglx recording
        suppress_data_move (bool): can set to True for testing
    """

    # Make new subdirectory for data in session-level directory
    if "catgt" in sglx_session_path.name:
        ephys_dir_name = "ephys_catgt"
    else:
        ephys_dir_name = "ephys_sglx"
    ephys_dir = get_session_subdir(session_dir, ephys_dir_name)
    sglx_dst = ephys_dir / sglx_session_path.name

    # Don't copy if sglx recording dir already exists in same location
    if sglx_dst.exists():
        return
    
    if suppress_data_move:  # for testing file structure
        return
    
    # Move data if it's on the same disk as the new dir
    print(f"{session_dir.name} -- Moving SGLX data.")
    if sglx_session_path.stat().st_dev == ephys_dir.stat().st_dev:
        shutil.move(sglx_session_path, sglx_dst)
    # Copy data if it's on a separate disk
    else:
        shutil.copytree(sglx_session_path, sglx_dst)
    print(f"{session_dir.name} -- Moved SGLX data.")


def find_sglx_recordings(search_str: str="", source_path=SGLXDATA_PATH) -> list:
    """Find SpikeGLX recording directories in source_path."""
    possible_dirs = [d for d in source_path.iterdir() if d.is_dir() and search_str in d.name]
    imec_dirs = []
    for possible_dir in possible_dirs:
        if any([("imec" in d.name) for d in possible_dir.iterdir()]):
            imec_dirs.append(possible_dir)
    return imec_dirs


def import_behavior_data(session_dir: Path, rec_datetime: datetime, subject_id: str=None,
                         source_path=BEHAVIOR_PATH, suppress_data_move=False):
    """
    Copies behavior data to session directory.
    
    Parameters:
        session_dir (Path): session-level path 
        rec_datetime (datetime): datetime object extracted from sglx recording metadata
        subject_id (str): subject id string
        source_path (Path): location of behavior data
        suppress_data_move (bool): can set to True for testing
    """

    # Find original behavior file
    behavior_src_path = find_behavior_file("behavior", rec_datetime, subject_id, source_path=source_path)
    if behavior_src_path is None:
        print(f"{session_dir.name} -- No behavior file found.")
        return

    # Make behavior subdirectory in session dir
    behavior_dir = get_session_subdir(session_dir, "behavior")
    behavior_raw_dst = behavior_dir / behavior_src_path.name
    if behavior_raw_dst.exists():
        return
    
    if suppress_data_move:  # for testing file structure
        return

    # Copy behavior file
    if behavior_src_path.is_dir():
        shutil.copytree(behavior_src_path, behavior_raw_dst)
    else:
        shutil.copy(behavior_src_path, behavior_raw_dst)
    print(f"{session_dir.name} -- Copied behavior data.")


def import_video_data(session_dir: Path, rec_datetime: datetime, subject_id: str=None,
                      source_path=VIDEO_PATH, copy_only=False, suppress_data_move=False):
    """
    Moves or copies video data to session directory.

    Parameters:
        session_dir (Path): session-level path 
        rec_datetime (datetime): datetime object extracted from sglx recording metadata
        subject_id (str): subject id string
        source_path (Path): location of video data
        copy_only (bool): never move data, just copy from source to destination
        suppress_data_move (bool): can set to True for testing
    """

    # Find matching video data
    video_src_path = find_behavior_file("video", rec_datetime, subject_id, source_path=source_path)
    if video_src_path is None:
        print(f"{session_dir.name} -- No video data found.")
        return
    
    # Make video data subdir in session dir
    video_dir = get_session_subdir(session_dir, "video")
    video_dst_path = video_dir / video_src_path.name
    if video_dst_path.exists():
        return    

    if suppress_data_move:  # for testing file structure
        return

    print(f"{session_dir.name} -- Organizing video data.")
    # If video is stored on the same disk as destination, just move it.
    if (source_path.stat().st_dev == video_dir.stat().st_dev) and not copy_only:
        shutil.move(video_src_path, video_dst_path)
        print(f"{session_dir.name} -- Moved video data.")
        return
    
    # Otherwise make a copy
    if video_src_path.is_dir():
        shutil.copytree(video_src_path, video_dst_path)
    else:
        shutil.copy(video_src_path, video_dst_path)
    print(f"{session_dir.name} -- Copied video data.")


def find_behavior_file(key: str, recording_dt: datetime, subject_id: str=None,
                       threshold_seconds=3*60, retsingle=True, source_path=None) -> Path:
    """Find behavior csv or video file for a given subject and session datetime."""
    
    # Select source path and format a regex search pattern for this session
    if key=="behavior":
        source_path = BEHAVIOR_PATH if (source_path is None) else source_path
    elif key=="video":
        source_path = VIDEO_PATH if (source_path is None) else source_path

    # Find possible behavior files for recording session
    possible_matches = []
    for filepath in source_path.iterdir():
        # Compare subjects
        if (subject_id is not None) and (subject_id not in filepath.name):
            continue

        # Get file date
        dt_string = re.search(BEHAVIOR_PATTERNS[key]["dt_regex"], filepath.name)
        if dt_string is None:
            continue
        behavior_dt = datetime.strptime(dt_string, BEHAVIOR_PATTERNS[key]["dt_format"])

        # Compare file create time to recording time
        if abs(behavior_dt - recording_dt).total_seconds() < threshold_seconds:
            possible_matches.append(filepath)

    if len(possible_matches)==1:
        return possible_matches[0]
    elif len(possible_matches)==0:
        return None
    if not retsingle:
        return possible_matches
    else:
        print(f"    More than one possible behavior file found.")
        return None


def get_session_subdir(session_path: Path, key: str=None) -> Path:
    """
    Return subdirectory in session_path called <key>.
    Always makes new subdirectory if it doesn't exist already.
    """
    if key is None:
        subdir_path = session_path
    else:
        subdir_path = session_path / key
    if not subdir_path.exists():
        os.mkdir(subdir_path)
    return subdir_path
