import sys
from pathlib import Path
from datetime import date
from .config import *
from .spikeglx_utils import find_meta_path, readMeta, MetaToCoords

try:
    from kilosort import run_kilosort
    from kilosort.io import load_probe
except ImportError:
    print(f"Kilosort not available.")


def main():
    if len(sys.argv) != 2:
        print(f"Incorrect number of inputs.")
        return 1
    elif len(sys.argv) == 2:
        recording_path = Path(sys.argv[1])
        if not recording_path.exists():
            return 2
        sorting = Sorting(recording_path)
        return sorting.status


class Sorting:
    """
    Prepare recording metadata and run kilosort for one recording.
    Parameters:
        recording_dir (Path): SpikeGLX probe-level recording folder
    """
    def __init__(self, recording_path: Path):
        self.status = 99

        self.recording_path = Path(recording_path)
        if not self.recording_path.exists():
            raise IOError(f"{self.recording_path.name}  Recording not found.")
        self.metadata_path = find_meta_path(self.recording_path)
        self.metadata = readMeta(self.metadata_path)

        # Find or make channel map
        if self._find_channelmap() is None:
            self._make_channelmap()
        
        # Create kilosort probe object
        probe_params = load_probe(self.channel_map)

        # Set kilosort settings
        settings = {
            "data_dir": self.recording_path,
            "n_chan_bin": 385,
            "fs": float(self.metadata["imSampRate"]),
            "nearest_chans": 10,  # n-trode number
        }
        if not DRIFT_CORRECTION:
            settings["nblocks"] = 0

        # Format results dir path
        self.results_dir = (
            self.recording_path / f"{date.today().strftime(r'%Y%m%d')}_kilosort4"
        )

        # Run sorting
        run_kilosort(
            settings=settings,
            probe=probe_params,
            do_CAR=(not CATGT_CAR),
            results_dir=self.results_dir,
        )

        self.status = 0

    def _find_channelmap(self):
        """Find probe channel map path."""

        channel_map_files = [
            f for f in self.recording_path.iterdir()
            if "kilosort_channel_map" in f.name
        ]

        if len(channel_map_files) == 0:
            self.channel_map = None
            return self.channel_map
        
        elif len(channel_map_files) > 1:
            print(f"More than one kilosort channel map file found, using first.")

        self.channel_map = self.recording_path / channel_map_files[0]

        return self.channel_map

    def _make_channelmap(self):
        """Generate channel map required for kilosort."""

        # Create channel map json for kilosort
        MetaToCoords(metaFullPath=self.metadata_path, outType=1, showPlot=False)

        # Create numpy array of coords for reference
        MetaToCoords(metaFullPath=self.metadata_path, outType=2, showPlot=False)

        # Get channelmap path
        if self._find_channelmap() is None:
            raise IOError(f"{self.recording_path.name}  Channel map not found.")