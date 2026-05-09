import sys
from pathlib import Path
from datetime import date
from kilosort import run_kilosort
from kilosort.io import load_probe
from .sglx_metadata import find_meta_path, readMeta, MetaToCoords

def make_channelmap(recording_path: Path):
    """Generate channel map required for kilosort."""

    # Find metadata file
    meta_path = find_meta_path(recording_path)

    # Create channel map json for kilosort
    MetaToCoords(metaFullPath=meta_path, outType=1, showPlot=False)
    
    # Create numpy array of coords for reference
    MetaToCoords(metaFullPath=meta_path, outType=2, showPlot=False)

    return 0

def find_channelmap(recording_path: Path) -> Path:
    """Find probe channel map path."""

    channel_map_files = [f for f in recording_path.iterdir() if "kilosort_channel_map" in f.name]

    if len(channel_map_files)==0:
        return None
    elif len(channel_map_files)>1:
        print(f"More than one kilosort channel map file found, using first.")
    
    return recording_path / channel_map_files[0]

def prep_run_kilosort(recording_dir: Path, do_CAR=False, do_drift_correction=True):
    """
    Prepare recording metadata and run kilosort for one recording.

    Parameters:
        recording_dir (Path): SpikeGLX probe-level recording folder
        do_CAR (bool): You must apply CAR (set do_CAR=True) if it was not applied by CatGT
        do_drift_correction (bool): disable drift correction
    """

    # Find or make channel map
    channel_map = find_channelmap(recording_dir)
    if channel_map is None:
        make_channelmap(recording_dir)
        channel_map = find_channelmap(recording_dir)
    
    # Create kilosort probe object
    probe_params = load_probe(channel_map)
    
    # Set kilosort settings
    recording_metadata = readMeta(find_meta_path(recording_dir))
    settings = {"data_dir": recording_dir,
                "n_chan_bin": 385,
                "fs": float(recording_metadata["imSampRate"]),
                "nearest_chans": 10,  # was using 12
                "Th_universal": 12,  # default: 9
                }
    if not do_drift_correction:
        settings["nblocks"] = 0
    
    # Format results dir path
    results_dir = recording_dir / f"{date.today().strftime(r'%Y%m%d')}_kilosort4"
    
    # Run kilosort
    run_kilosort(settings=settings, probe=probe_params, do_CAR=do_CAR, results_dir=results_dir)

def main():
    if len(sys.argv)!=2:
        print(f"Incorrect number of inputs.")
        return 1
    elif len(sys.argv)==2:
        recording_path = Path(sys.argv[1])
        if not recording_path.exists():
            return 2
        prep_run_kilosort(recording_path)
        return 0

if __name__=="__main__":
    main()