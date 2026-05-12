import os
from .config import *
from .session_state_log import find_sessions


def main():
    """Run phy in script."""

    # Find sorted sessions that have not been curated
    session_names = find_sessions(
        search_dict={"kilosort_bool": True, "phy_bool": False}
    )

    # Select next available session
    next_session_name = session_names[0]

    # Run phy
    run_phy(next_session_name, probe=0, force_waveforms=False)


def run_phy(
    session_search_key: str,
    probe: int,
    session_source: Path = SESSIONS_PATH,
    sorting_name: str = None,
    force_waveforms=False,
):
    """
    Run phy gui for manual spike curation.

    Params:
        session_search_key (str): name of session to curate
        probe (int): probe number
        root (Path): session-level folders to search in
        sorting_name (str): must be exact match, or set to None for most recent sorting
        force_waveforms (bool): force run extract waveform function
    """

    if not isinstance(session_search_key, str):
        raise ValueError("Search key is not a string.")

    # Find session
    session_dirs = [
        d
        for d in session_source.iterdir()
        if (session_search_key in d.name) and (d.is_dir())
    ]
    if len(session_dirs) == 0:
        print(f"No sessions found.")
        return
    elif len(session_dirs) > 1:
        print(f"More than one session found.")
        return
    session_recording_dir = [
        d for d in (session_dirs[0] / "ephys_catgt").iterdir() if d.is_dir()
    ][0]
    recording_path = [
        d
        for d in session_recording_dir.iterdir()
        if (f"imec{probe}" in d.name) and (d.is_dir())
    ][
        0
    ]  # type: Path

    # Find sorting folder
    sorting_paths = [p for p in recording_path.iterdir() if "kilosort4" in p.name]
    if len(sorting_paths) == 0:
        raise IOError("No sortings found.")
    if sorting_name is None:
        ksout_path = sorting_paths[-1]  # Select most recent sorting
    else:
        ksout_path = recording_path[probe] / str(sorting_name)

    # Find kilosort params
    params_path = ksout_path / "params.py"

    # Extract waveforms if phy has not been run before on this session
    if (not ".phy" in next(os.walk(ksout_path))[1]) or force_waveforms:
        os.system(f"phy extract-waveforms {params_path}")

    # Run phy
    os.system(f"phy template-gui {params_path}")


if __name__ == "__main__":
    main()
