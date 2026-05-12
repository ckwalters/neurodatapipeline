"""
Functions for creating, maintaining, and searching neurodata pipeline
processing state log json (STATES_PATH).

session_states fields:
    ["session_name", "mouse_name", "datetime", "n_probes", "sglx_bool", "sglx_name", 
    "behavior_bool", "behavior_name", "video_bool", "video_name", 
    "catgt_bool", "catgt_name", "tprime_bool", "kilosort_bool", "phy_bool", 
    "sa_bool", "lfp_bool", "lfp_dfs_bool",]
"""

import json
import pandas as pd
from pathlib import Path
from .pipeline_io import find_file
from .config import *


def check_data(search_path: Path, key: str):
    """Check whether specific data type exists at path."""

    entry = {}

    data_dir = find_file(search_path, key)
    if data_dir is None or (not any(data_dir.iterdir())):
        entry[f"{key}_bool"] = False
        entry[f"{key}_name"] = None
    else:
        if key in ["sglx", "catgt", "video"]:  # looking for folder
            file = find_file(data_dir)
        elif key in ["behavior"]:
            file = [f for f in data_dir.iterdir() if ".csv" in f.name][0]
        entry[f"{key}_bool"] = True
        entry[f"{key}_name"] = file.name

    return entry


def check_processing(rec_session_dir: Path):
    """Check whether processing step has occured."""

    state_dict = {}

    # Tprime
    if len([f for f in rec_session_dir.iterdir() if "synced" in f.name]) > 0:
        state_dict["tprime_bool"] = True
    else:
        state_dict["tprime_bool"] = False

    # Individual probe recordings
    rec_dirs = [d for d in rec_session_dir.iterdir() if "imec" in d.name]
    state_dict["n_probes"] = len(rec_dirs)

    # Check each sorting step
    ks_status = 0
    phy_status = 0
    sa_status = 0
    lfp_status = 0
    lfp_dfs_status = 0
    for rec_dir in rec_dirs:
        # Kilosort
        ks_dir = find_file(rec_dir, "kilosort4", verbose=False)
        if ks_dir is None:
            ks_status += 1
            phy_status += 1
            sa_status += 1
        else:
            # Phy
            if len([f for f in ks_dir.iterdir() if "phy" in f.name]) == 0:
                phy_status += 1
            else:
                cluster_info = pd.read_csv(ks_dir / "cluster_info.tsv", sep="\t")
                if pd.isna(cluster_info["group"]).sum() > 5:
                    phy_status += 1

            # Sorting analyzer
            sa_dir = find_file(ks_dir, "sorting_analyzer", verbose=False)
            if sa_dir is None:
                sa_status += 1

        # LFP
        lfp_dir = find_file(rec_dir, "lfp")
        if lfp_dir is None or (not any(lfp_dir.iterdir())):
            lfp_status += 1
            lfp_dfs_status += 1
        else:
            if len([f for f in lfp_dir.iterdir() if "lfp_df" in f.name]) == 0:
                lfp_dfs_status += 1

    if ks_status == 0:
        state_dict["kilosort_bool"] = True
    else:
        state_dict["kilosort_bool"] = False

    if phy_status == 0:
        state_dict["phy_bool"] = True
    else:
        state_dict["phy_bool"] = False

    if sa_status == 0:
        state_dict["sa_bool"] = True
    else:
        state_dict["sa_bool"] = False

    if lfp_status == 0:
        state_dict["lfp_bool"] = True
    else:
        state_dict["lfp_bool"] = False

    if lfp_dfs_status == 0:
        state_dict["lfp_dfs_bool"] = True
    else:
        state_dict["lfp_dfs_bool"] = False

    return state_dict


def check_session(session_dir: Path):
    """
    Check which data exists in session-level folder and what
    processing steps have occured.
    """

    state_dict = {}

    # Session metadata
    state_dict["session_name"] = session_dir.name
    state_dict["mouse_name"] = state_dict["session_name"][0:5]
    state_dict["datetime"] = "_".join(state_dict["session_name"].split("_")[1:])
    state_dict["n_probes"] = None

    # Basic data types
    for data_key in ["sglx", "behavior", "video", "catgt"]:
        state_dict.update(check_data(session_dir, data_key))

    # Data processing steps
    if state_dict["catgt_bool"]:
        # Session recording folder
        rec_session_dir = session_dir / "ephys_catgt" / state_dict["catgt_name"]
        state_dict.update(check_processing(rec_session_dir))

    return state_dict


def update_session_states(root=SESSIONS_PATH, save=True):
    """Search through all sessions in root and log pipeline steps for each session."""

    if STATES_PATH.exists():
        with open(STATES_PATH, "r") as states_file:
            session_states = json.load(states_file)
    else:
        session_states = {}

    session_paths = [d for d in root.iterdir() if d.is_dir()]
    for session_path in session_paths:
        if session_path.name not in session_states.keys():
            session_states[session_path.name] = check_session(session_path)
        else:
            session_states[session_path.name].update(check_session(session_path))

    # Save
    if save:
        json_states = json.dumps(session_states, indent=4)
        with open(STATES_PATH, "w") as states_file:
            states_file.write(json_states)


def find_sessions(search_dict={}, mode="all", update=False):
    """
    Search for sessions in session state log matching key/bool
    pairs in search_dict.
    Parameters:
        search_dict (dict): key (states log key) value (bool) pairs
        update (bool): if True, write updates to .json file
    """

    # Default to all false (no processing steps completed)
    if not search_dict:
        keys = [
            "catgt_bool",
            "tprime_bool",
            "kilosort_bool",
            "phy_bool",
            "sa_bool",
            "lfp_bool",
            "lfp_dfs_bool",
        ]
        flags = [False] * len(keys)
        search_dict = dict(zip(keys, flags))

    if (not STATES_PATH.exists()) or update:
        update_session_states()

    # Read states log from disk
    with open(STATES_PATH, "r") as states_file:
        session_states = json.load(states_file)  # type: dict

    # Search for sessions matching criteria
    sessions_found = []
    for session_name in session_states.keys():
        # Collect keys that match the search_dict bool value
        add_flags = []
        for key in search_dict.keys():
            add_flags.append(session_states[session_name][key] == search_dict[key])

        # Add session depending on match mode
        if mode == "all" and all(add_flags):
            sessions_found.append(session_name)
        elif mode == "any" and any(add_flags):
            sessions_found.append(session_name)

    return sessions_found


def search_sessions(
    search_all=True, search_key="", nodes=None, mode="all", source_dir=SESSIONS_PATH
):
    """Search for sessions either by search string or by states log."""

    # Search all sessions; optionally matching search key
    if search_all:
        session_paths = [
            d for d in source_dir.iterdir() if d.is_dir() and (search_key in d.name)
        ]
        if len(session_paths) == 0:
            return None
        return session_paths

    # Select sessions based on which processing steps are needed
    if nodes is not None:
        search_keys = [f"{node}_bool" for node in nodes]
    else:
        search_keys = None
    # Find sessions where pipeline steps have not been completed
    session_names = find_sessions(
        search_dict=dict(zip(search_keys, [False] * len(search_keys))), mode=mode
    )
    session_paths = [source_dir / n for n in session_names]
    if len(session_paths) == 0:
        return None

    return session_paths
