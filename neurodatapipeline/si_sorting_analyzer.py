import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import spikeinterface.full as si
import spikeinterface.extractors as se
import spikeinterface.qualitymetrics as sqm
import spikeinterface.curation as sc
import spikeinterface.widgets as sw
from pathlib import Path
from .config import *


si.set_global_job_kwargs(**dict(n_jobs=16))


def main():
    if len(sys.argv) != 2:
        print(f"Incorrect number of inputs.")
        return 1
    elif len(sys.argv) == 2:
        node_sortinganalyzer(sys.argv[1])
        return 0


def node_sortinganalyzer(recording_path: Path):
    """Create sorting analyzer from recording path."""

    SuperAnalyzer(recording_path, make_plots=MAKE_QC_PLOTS)


class SuperAnalyzer:
    def __init__(
        self,
        recording_path: Path,
        sorting_str: str = None,
        analyzer_name: str = "sorting_analyzer",
        make_plots=False,
    ):

        """
        Wrapper class for spikeinterface sorting analyzer and plotting functions.
        Parameters:
            recording_path (Path): single-probe recording subdirectory
            sorting_str (str): name of sorting instance (if None, latest sorting will be selected)
            analyzer_name (str): name of sorting analyzer generated
            make_plots (bool): generates and saves unit quality control plots
        """

        # Recording path
        self.recording_path = Path(recording_path)

        # Probe name
        self.probe = str(self.recording_path.name)[-1]

        # Find sorting
        if sorting_str is None:
            # Most recent sorting
            sorter_dir = [
                dir for dir in os.listdir(self.recording_path) if "kilosort4" in dir
            ][-1]
        else:
            sorter_dir = str(sorting_str)
        self.sorting_path = self.recording_path / sorter_dir

        # Load or make analyzer
        self.analyzer_path = self.sorting_path / analyzer_name
        self.analyzer_loaded = False
        if not os.path.exists(self.analyzer_path):
            # Make new sorting analyzer
            self.analyzer_loaded = self.make_sorting_analyzer()
        else:
            # Load existing sorting analyzer
            self.analyzer_loaded = self.load_sorting_analyzer()

        if not self.analyzer_loaded:
            raise IOError()

        # Make dataframe with all desired unit metrics
        formatted = self.format_unit_metrics()

        # Curate units
        curated = self.curate_units()

        # Export unit data
        self.unit_info.to_csv(self.analyzer_path / "unit_info.csv")

        # Make unit quality control figures
        if make_plots and formatted:
            if not os.path.exists(self.sorting_path / "qc_figures"):
                os.mkdir(self.sorting_path / "qc_figures")
            self.make_qc_plots(export=True)

    def make_sorting_analyzer(self, apply_CMR=False):
        """Create new sorting analyzer for one probe recording/kilosort sorting."""

        # Load recording
        recording = se.read_spikeglx(
            self.recording_path, stream_id=f"imec{self.probe}.ap"
        )
        # Must highpass filter because spikeinterface needs to extract waveforms from the raw data
        recording = si.bandpass_filter(recording, freq_min=300, freq_max=6000)
        # Add CMR if it hasn't already been done to your SGLX data
        if apply_CMR:
            recording = si.common_reference(
                recording, reference="global", operator="median"
            )

        # Load sorting
        # NOTE: se.read_kilosort() will load phy labels by reading in cluster_info.tsv columns as properties
        sorting = se.read_kilosort(folder_path=self.sorting_path)

        # Make sorting analyzer and do all the computations
        sorting_analyzer = si.create_sorting_analyzer(
            sorting=sorting,
            recording=recording,
            sparse=True,
            format="binary_folder",
            folder=self.analyzer_path,
        )

        sorting_analyzer.compute("random_spikes")
        sorting_analyzer.compute("waveforms", ms_before=1.0, ms_after=1.5)
        sorting_analyzer.compute("templates")
        sorting_analyzer.compute("noise_levels")
        sorting_analyzer.compute("correlograms")
        sorting_analyzer.compute("unit_locations")
        sorting_analyzer.compute("spike_amplitudes")
        sorting_analyzer.compute("template_similarity")
        sorting_analyzer.compute("template_metrics")

        sqm.compute_quality_metrics(
            sorting_analyzer,
            metric_names=["firing_rate", "amplitude_median", "snr", "isi_violation"],
        )

        self.sorting_analyzer = sorting_analyzer

        return True

    def load_sorting_analyzer(self):
        """Load previously made sorting analyzer."""

        self.sorting_analyzer = si.load_sorting_analyzer(self.analyzer_path)

        return True

    def format_unit_metrics(self):
        """Get unit and sorting analyzer data & format into dataframe."""

        # Unit metadata (inherited from cluster_info.tsv)
        unit_index = self.sorting_analyzer.sorting.get_unit_ids()
        unit_ids = pd.Series(
            self.sorting_analyzer.sorting.get_unit_ids(),
            index=unit_index,
            name="unit_id",
        )
        shanks = pd.Series(
            self.sorting_analyzer.sorting.get_property("sh"),
            index=unit_index,
            name="shank",
        )
        channels = pd.Series(
            self.sorting_analyzer.sorting.get_property("ch"),
            index=unit_index,
            name="channel",
        )
        depths = pd.Series(
            self.sorting_analyzer.sorting.get_property("depth"),
            index=unit_index,
            name="depth",
        )

        # Quality metrics
        quality_metrics = self.sorting_analyzer.get_extension(
            "quality_metrics"
        ).get_data()

        # Template metrics
        template_metrics = self.sorting_analyzer.get_extension(
            "template_metrics"
        ).get_data()

        # Kilosort label (inherited from cluster_info.tsv)
        kilosort_label = pd.Series(
            self.sorting_analyzer.sorting.get_property("KSLabel"),
            index=unit_index,
            name="ks_label",
        )

        # Make dataframe
        self.unit_info = pd.concat(
            [
                unit_ids,
                shanks,
                channels,
                depths,
                quality_metrics,
                template_metrics,
                kilosort_label,
            ],
            axis=1,
        )

        # Find redundant pairs
        self.unit_info["duplicate_id"] = pd.NA
        redundant_pairs = sc.find_redundant_units(self.sorting_analyzer.sorting)
        for (unit_a, unit_b) in redundant_pairs:
            self.unit_info.loc[
                self.unit_info["unit_id"] == unit_a, "duplicate_id"
            ] = unit_b
            self.unit_info.loc[
                self.unit_info["unit_id"] == unit_b, "duplicate_id"
            ] = unit_a

        return True

    def curate_units(self, phy=PHY_CURATION, auto=AUTO_CURATION):
        """Label units as 'good' based on phy curation and/or calculated metrics."""

        # Manual curation with phy
        if phy:
            unit_index = self.sorting_analyzer.sorting.get_unit_ids()
            phy_label = pd.Series(
                self.sorting_analyzer.sorting.get_property("quality"),
                index=unit_index,
                name="phy_label",
            )
            self.unit_info = pd.concat([self.unit_info, phy_label], axis=1)

        # Automatic curation based on metrics
        if auto:
            # TODO implement auto curation
            pass

        # Store list of good units
        self.good_units = []
        if "phy_label" in self.unit_info.columns:
            self.good_units = self.unit_info.loc[
                self.unit_info["phy_label"] == "good", "unit_id"
            ].to_list()

        return True

    def make_qc_plots(self, good_only=True, export=True):
        """Make qc plots for units."""

        print(f"{self.recording_path.name} -- Making QC unit plots.")

        # Select units to plot
        if good_only:
            unit_list = self.good_units
        else:
            unit_list = self.unit_info["unit_id"].to_list()

        # Plot each unit
        for unit in unit_list:
            self.plot_unit_summary(unit, export=export)

    def plot_unit_summary(
        self,
        unit,
        plot_all_clusters=True,
        export=False,
        unit_color="k",
        good_color="mediumturquoise",
    ):

        # Styling
        micro = "\u00B5"

        # Make canvas
        fig = plt.figure(figsize=(10, 8))
        gs = gridspec.GridSpec(3, 3)

        # Waveforms on probe
        ax = fig.add_subplot(gs[:, 0])
        sw.plot_unit_waveforms(
            self.sorting_analyzer,
            unit_ids=[unit],
            same_axis=True,
            ax=ax,
            unit_colors={unit: "gray"},
            alpha_waveforms=0.2,
            lw_templates=1,
            plot_legend=False,
        )
        ax.set_ylabel(f"Depth on Probe ({micro}m)")
        # ax.set_yticks([])
        ax.set_xticks([])
        ax.set_title(f"Waveforms Across Channels", fontsize=11)

        # Best channel waveforms in microvolts
        ax = fig.add_subplot(gs[0, 1])
        self.plot_waveforms(unit, ax)

        # Autocorrelogram
        ax = fig.add_subplot(gs[0, 2])
        sw.plot_autocorrelograms(
            self.sorting_analyzer, unit_ids=[unit], unit_colors={unit: "gray"}, ax=ax
        )
        ax.axvline(-3, lw=0.5, color="k", ls="dashed")
        ax.axvline(3, lw=0.5, color="k", ls="dashed")
        ax.set_ylabel(f"")
        ax.set_xlim(-25, 25)
        ax.set_xlabel(f"Time (ms)")
        ax.set_title(f"Autocorrelogram", fontsize=11)

        # Probe map
        ax = fig.add_subplot(gs[1, 1])
        if plot_all_clusters:
            bad_units = self.unit_info.loc[
                ((self.unit_info.index != unit) & (self.unit_info.phy_label != "good"))
            ].index
            good_units = self.unit_info.loc[
                ((self.unit_info.index != unit) & (self.unit_info.phy_label == "good"))
            ].index
            for unit_list, color in zip([bad_units, good_units], ["gray", good_color]):
                sw.plot_unit_locations(
                    self.sorting_analyzer,
                    unit_ids=unit_list,
                    ax=ax,
                    unit_colors=dict(zip(unit_list, [color] * len(unit_list))),
                    plot_all_units=False,
                )
            sw.plot_unit_locations(
                self.sorting_analyzer,
                unit_ids=[unit],
                ax=ax,
                unit_colors={unit: unit_color},
                plot_all_units=False,
            )
        else:
            sw.plot_unit_locations(
                self.sorting_analyzer, unit_ids=[unit], unit_colors={unit: "k"}, ax=ax
            )
        ax.set_xlabel(f"{micro}m", fontsize=10)
        ax.set_ylabel(f"{micro}m", fontsize=10)
        ax.set_title(f"Unit Location on Probe", fontsize=11)

        # Unit cell type characteristics
        ax = fig.add_subplot(gs[1, 2])
        if plot_all_clusters:
            ax.scatter(
                self.unit_info.loc[self.unit_info.phy_label != "good", "firing_rate"],
                self.unit_info.loc[self.unit_info.phy_label != "good", "peak_to_valley"]
                * 1000,
                10,
                c="gray",
                alpha=0.1,
            )
            ax.scatter(
                self.unit_info.loc[self.unit_info.phy_label == "good", "firing_rate"],
                self.unit_info.loc[self.unit_info.phy_label == "good", "peak_to_valley"]
                * 1000,
                10,
                c="darkturquoise",
                alpha=0.5,
            )
        ax.scatter(
            self.unit_info.loc[unit, "firing_rate"],
            self.unit_info.loc[unit, "peak_to_valley"] * 1000,
            20,
            c="k",
        )
        ax.set_ylim(0, 2)
        ax.set_title(f"FR vs Spike Width", fontsize=11)
        ax.set_xlabel(f"Firing Rate (Hz)")
        ax.set_ylabel(f"Peak to Valley (ms)")

        # Spike amplitude over time
        ax = fig.add_subplot(gs[2, 1:3])
        if plot_all_clusters:
            self.plot_amplitudes(ax, unit, unit_color, good_color)
        else:
            sw.plot_amplitudes(
                self.sorting_analyzer,
                unit_ids=[unit],
                ax=ax,
                unit_colors={unit: "gray"},
                plot_legend=False,
            )
        ax.set_title(f"Spike Amplitude Over Time", fontsize=11)
        ax.set_ylabel(f"Amplitude (uV)")
        ax.set_xlabel(f"Time (s)")

        # Style canvas
        unit_name = (int(self.probe) + 1) * 1000 + unit
        fig.suptitle(
            f"Probe {self.probe} Unit {unit_name}    {self.recording_path.name}",
            fontsize=11,
        )
        fig.tight_layout()

        # Save
        if export:
            fig.savefig(
                self.sorting_path
                / "qc_figures"
                / f"{self.recording_path.name}_{unit_name}",
                dpi=300,
            )
            plt.close()
        else:
            plt.show()

    def plot_amplitudes(self, ax: plt.Axes, unit: int, unit_color, good_color):
        """Plot amplitude of unit on its best channel across time with other units as background."""

        # Find data
        channel_coords = self.sorting_analyzer.recording.get_channel_locations()
        unit_channel = self.unit_info.loc[unit, "channel"]
        unit_x = channel_coords[unit_channel][0]
        unit_y = channel_coords[unit_channel][1]
        neighbor_chs = np.where(
            (
                (np.abs(unit_x - channel_coords[:, 0]) <= 15)
                & (np.abs(unit_y - channel_coords[:, 1]) <= 15)
            )
        )[0]

        # Get same-channel units
        bad_units = self.unit_info.loc[
            (
                (self.unit_info.channel.isin(neighbor_chs))
                & (self.unit_info.index != unit)
                & (self.unit_info.phy_label != "good")
            )
        ].index
        good_units = self.unit_info.loc[
            (
                (self.unit_info.channel == self.unit_info.channel.loc[unit])
                & (self.unit_info.index != unit)
                & (self.unit_info.phy_label == "good")
            )
        ].index

        # Plot all background units
        for unit_list, color in zip([bad_units, good_units], ["gray", good_color]):
            sw.plot_amplitudes(
                self.sorting_analyzer,
                unit_ids=unit_list,
                ax=ax,
                scatter_decimate=10,
                unit_colors=dict(zip(unit_list, [color] * len(unit_list))),
                plot_legend=False,
            )

        # Plot selected unit
        sw.plot_amplitudes(
            self.sorting_analyzer,
            unit_ids=[unit],
            ax=ax,
            unit_colors={unit: unit_color},
            plot_legend=False,
        )

        ax.set_ylim(self.unit_info.loc[unit, "amplitude_median"] * 1.8, 0)

    def plot_waveforms(self, unit_id, ax, linecolor="gray", linealpha=0.05):
        """Plot waveforms for single unit in microvolts."""

        # Find best channel for unit
        unit_channels = self.sorting_analyzer.sparsity.unit_id_to_channel_indices[unit_id]  # type: ignore
        best_channel = si.get_template_extremum_channel(
            self.sorting_analyzer, outputs="index"
        )[unit_id]
        best_channel_idx = np.where(unit_channels == best_channel)[0][0]

        # Get waveforms
        wf_ext = self.sorting_analyzer.get_extension("waveforms")
        wfs = wf_ext.get_waveforms_one_unit(unit_id, force_dense=False)  # type: ignore
        best_wfs = wfs[
            :, :, best_channel_idx
        ].transpose()  # rows: samples, cols: waveforms (105, 500)

        # Get median waveform
        median_wf = np.median(best_wfs, axis=1)

        # Convert samples to milliseconds ms_before=1.0, ms_after=1.5)
        wfs_ms_window = (
            wfs.shape[1] / self.sorting_analyzer.recording.sampling_frequency * 1000
        )
        if np.isclose(wfs_ms_window, 2.5):
            times = np.linspace(-1.0, 1.5, best_wfs.shape[0])  # times in miliseconds
        else:
            print(
                f"Waveform window not 2.5 ms, plotting aligned to beginning of window."
            )
            times = np.linspace(
                0, wfs_ms_window, best_wfs.shape[0]
            )  # times in miliseconds
        all_times = np.repeat(times[:, np.newaxis], best_wfs.shape[1], axis=1)

        # Plot waveforms
        ax.plot(all_times, best_wfs, c=linecolor, lw=0.5, alpha=linealpha)
        ax.plot(times, median_wf, c="k", lw=1)

        # Style
        ax.set_xlim(-1.0, 1.5)
        ax.set_xlabel(f"Time (ms)")
        micro = "\u00B5"
        ax.set_ylabel(f"Amplitude ({micro}V)")
        ax.set_title(f"Waveforms on Ch {best_channel}", fontsize=11)
