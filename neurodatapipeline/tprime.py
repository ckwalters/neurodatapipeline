import subprocess
import numpy as np
from config import *
from pipeline_io import find_file


def tprime_pipeline_node(session_path: Path):
    """Run tprime on session_path."""

    print(f"{session_path.name} -- Running TPrime")

    # Generate tprime command
    command = tprime_command(session_path)

    # Run as subprocess
    status = run_tprime(command)

    return status


def run_tprime(command: str, tprime_path: Path = TPRIME_PATH):
    """Run tprime as subprocess"""

    # Format command
    full_command = f"cd {str(tprime_path)} && {command}"

    # Run
    status = subprocess.run(
        [part.strip() for part in full_command.split(" ")],
        capture_output=True,
        text=True,
        shell=True,
    )

    return status.returncode


def tprime_command(session_path: Path, event_bits=[1, 2], sorter="kilosort"):
    """
    Generates the command prompt line that will run tprime (v1.7) for the given run name.
    You don't need to sync sorted spike times if all probes were plugged in to the same headstage.
    You *do* still need to sync your imec and nidaq streams though, so still run this.
    Parameters:
        recording_path (Path): session-level folder
        event_bits (list): integer names of NIDQ bits to sync
    Returns:
        command (str): command to run TPrime
    """

    # TO stream (imec0)
    imec0_dir = find_file(session_path, key="imec0", is_dir=True)
    imec0_sync_path = find_file(imec0_dir, key="imec0.ap.xd_384_6_500.txt")

    # FROM streams
    # NIDQ
    ni_sync_path = find_file(session_path, key="nidq.xd_8_0_500.txt")
    ni_events_paths = [
        find_file(session_path, key=f"nidq.xd_8_{event_bit}_0.txt")
        for event_bit in event_bits
    ]
    ni_events = []
    for event_path in ni_events_paths:
        out_file = session_path / f"{event_path.name[0:-4]}_synced.txt"
        ni_events.append(f"-events=1,{str(event_path)},{str(out_file)}")

    # Additional probes
    # Find additional probe directories
    probe_dirs = find_file(session_path, key="imec", is_dir=True)
    if not isinstance(probe_dirs, list):
        probe_dirs = [probe_dirs]
    probe_dirs = [d for d in probe_dirs if "imec0" not in d.name]
    # Construct arguments
    addtl_probe_args = ""
    for probe_idx, probe_dir in enumerate(probe_dirs):
        if sorter == "kilosort":
            sorter_dir = find_file(probe_dir, "kilosort")
            imec_spiketimes = get_spikes_kilosort(sorter_dir)
        else:
            raise NotImplementedError()
        stream_index = probe_idx + 2  # stream 0 is imec0, stream 1 is reserved for NI
        out_file = f"{probe_dir.name[0:-4]}_spiketimes_synced.txt"
        addtl_probe_args += f"-fromstream={stream_index},{probe_dir} -events={stream_index},{imec_spiketimes},{out_file}"

    # Format command
    command = f"TPrime -syncperiod=1.0 -tostream={imec0_sync_path} -fromstream=1,{ni_sync_path} {' '.join(ni_events)} {' '.join(addtl_probe_args)}"

    return command


def get_spikes_kilosort(sorter_path: Path):
    """Convert kilosort output numpy spike times to .txt file."""

    # Load spike times
    spike_times = np.load(sorter_path / "spike_times.npy")

    # Make new spike times path
    spike_times_path = sorter_path / "spike_times.txt"

    # Make new spike times text document and write each spiketime
    with open(spike_times_path, "w") as f:
        for spike_time in spike_times:
            f.write(f"{int(spike_time)}\n")

    return spike_times_path
