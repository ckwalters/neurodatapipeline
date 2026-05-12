import subprocess
import pandas as pd
from pathlib import Path
from .config import *
from .pipeline_io import find_file, log
from .tprime import tprime_pipeline_node
from .catgt import catgt_pipeline_node

def pipeline(session_path: Path, nodes=None):
    """
    Run pipeline nodes.
    Codes 1X
    """
    if nodes is None:
        nodes = ["catgt", "tprime", "kilosort", "sa"]
    
    log("Running on session", p=session_path.name, n="pipeline", w=True)

    # Check if ephys data exists
    ephys_dirs = [d for d in session_path.iterdir() if d.is_dir() and "ephys" in d.name]
    if len(ephys_dirs)==0:
        log("No ephys folders found", p=session_path.name, n="pipeline", c=11, w=True)
        return 11
    
    ## SESSION-LEVEL NODES

    # End pipeline if catgt not called
    if "catgt" not in nodes:
        log("Catgt not called", session_path.name, 12)
        return 12
    
    # Check if catgt has been run, run if not
    cgt_status = node_catgt(session_path)
    if cgt_status==0:
        catgt_dir = find_file(session_path, "catgt")
    else:
        return cgt_status
    
    # Find recording session directory
    recording_dir = find_file(catgt_dir, "catgt")
    if recording_dir is None:
        log("No recording session folder found in ephys_catgt dir", p=session_path.name, n="pipeline", c=13, w=True)
        return 13

    # Check if tprime has been run, run if not
    if "tprime" in nodes:
        tp_status = node_tprime(recording_dir)

    # End pipeline if recording-level nodes are not called
    if ("kilosort" not in nodes) and ("sa" not in nodes):
        log("Kilosort/sorting analyzer not called", session_path.name, 14)
        return 14
    
    ## RECORDING-LEVEL NODES

    # Get probe recording paths
    probe_dirs = [d for d in recording_dir.iterdir() if d.is_dir() and "imec" in d.name]
    
    # Run single-probe pipeline processes
    probe_statuses = []
    for probe_dir in probe_dirs:
        probe_status = pipeline_probe(probe_dir, nodes=nodes)
        probe_statuses.append(probe_status)
    if sum(probe_statuses)!=0:
        log("Not all steps completed", session_path.name, 15)
        return 15

    log("All steps complete", session_path.name, 10, n="pipeline", w=True)
    return 0

def pipeline_probe(rec_dir: Path, nodes=["kilosort", "sa"]):
    """
    Run probe-specific pipeline processes (sorting, curation).
    Codes 2X
    """

    # Process lfp
    lfp_status = node_lfp(rec_dir)

    # Stop pipeline if kilosort not called for
    if "kilosort" not in nodes:
        return 21

    # Run kilosort node, break if error returned
    ks_status = node_kilosort(rec_dir)
    if ks_status!=0:
        return ks_status
    ks_dir = find_file(rec_dir, "kilosort4")
    
    if "sa" not in nodes:
        return 22

    # If phy is required, check if phy curation has occured, break if not
    if PHY_CURATION:
        phy_status = node_phy(ks_dir)
        if phy_status!=0:
            return phy_status

    # Run sorting analyzer node, break if error returned
    sa_status = node_sortinganalyzer(ks_dir)
    if sa_status!=0:
        return sa_status

    return 0

def node_catgt(session_dir: Path):
    """
    Node for running CatGT
    Codes 3X
    """

    # Check if CatGT has been run
    catgt_dir = find_file(session_dir, "catgt")
    if (catgt_dir is not None) and (any(catgt_dir.iterdir())):
        return 0
    
    # Check whether spikeglx data exists
    sglx_dir = find_file(session_dir, "sglx")
    if (sglx_dir is None) or (not any(sglx_dir.iterdir())):
        log("No sglx data found", p={session_dir.name}, c=31, n="catgt", w=True)
        return 31
    recording_session_dir = find_file(sglx_dir, "")

    # Run CatGT
    cgt_status = catgt_pipeline_node(recording_session_dir)
    if cgt_status==0:
        log("CatGT completed", p={session_dir.name}, c=30, n="catgt", w=True)
        return 0
    else:
        log("CatGT failed", p={session_dir.name}, c=32, n="catgt", w=True)
        return 32

def node_tprime(recording_dir: Path):
    """
    Node for running tprime.
    Codes 4X
    """
    session_name = recording_dir.parent.parent.name

    # Check whether tprime has been run
    if len([f for f in recording_dir.iterdir() if "synced" in f.name])>0:
        # assume past success, perhaps implement more checks
        return 0
    
    # Run TPrime
    tp_status = tprime_pipeline_node(recording_dir)
    if tp_status==0:
        log("TPrime completed", p=session_name, r=recording_dir.name, c=40, n="tprime", w=True)
        return 0
    else:
        log("TPrime failed", p=session_name, r=recording_dir.name, c=41, n="tprime", w=True)
        return 41

def node_kilosort(recording_dir: Path):
    """
    Node for running kilosort4.
    Codes 5X
    """
    session_name = recording_dir.parent.parent.name
    log("Running Kilosort", p=session_name, r=recording_dir.name, n="kilosort")

    ks_dir = find_file(recording_dir, "kilosort4")
    if ks_dir is not None:
        return 0
    
    # Run Kilosort
    ks_script_path = PIPELINE_PATH.parent / "run_kilosort4_sorting.py"
    ks_command = f"conda run -n {KS_ENV} python {str(ks_script_path)} {str(recording_dir)}"
    ks_status = subprocess.run(ks_command, capture_output=False, text=True, shell=True, errors="replace")
    if ks_status.returncode==0:
        log("Kilosort completed", p=session_name, r=recording_dir.name, c=50, n="kilosort", w=True)
        return 0
    else:
        log("Kilosort failed", p=session_name, r=recording_dir.name, c=51, n="kilosort", w=True)
        return 51

def node_phy(ks_dir: Path):
    """
    Check whether sorting has been curated in phy.
    Codes 6X
    """
    session_name = ks_dir.parent.parent.parent.name
    phy_files = [f for f in ks_dir.iterdir() if "phy" in f.name]
    
    # Phy never run
    if len(phy_files)==0:
        log("Phy not curated", p=session_name, r=ks_dir.name, c=61, n="phy", w=True)
        return 61
    
    # All units labeled
    # TODO: use csv instead of pandas
    cluster_info = pd.read_csv(ks_dir/"cluster_info.tsv", sep="\t")
    if pd.isna(cluster_info["group"]).sum() > 5:
        log("Phy not finished", p=session_name, r=ks_dir.name, c=62, n="phy", w=True)
        return 62

    log("Phy curated", p=session_name, r=ks_dir.name, c=60, n="phy", w=True)
    return 0

def node_sortinganalyzer(ks_dir: Path):
    """
    Node for running spikeinterface sorting analyzer.
    Codes 7X
    """
    session_name = ks_dir.parent.parent.parent.name
    log("Running Sorting Analyzer", p=session_name, r=ks_dir.name, n="sortinganalyzer")

    def check_sortinganalyzer_completed(ks_dir: Path):
        # Check for sorting analyzer path
        sa_dir = find_file(ks_dir, "sorting_analyzer")
        if sa_dir is None:
            return False
        
        # Check whether curation info has been exported in new format
        unit_info_path = sa_dir / "unit_info.csv"
        if not unit_info_path.exists():
            return False
        
        # Check whether QC plots have been made
        qc_plots_path = ks_dir / "qc_figures"  # type: Path
        if not qc_plots_path.exists():
            return False
        if not any(qc_plots_path.iterdir()):
            return False
        
        return True

    if check_sortinganalyzer_completed(ks_dir):
        return 0
    
    # Run sorting analyzer script
    sa_script_path = PIPELINE_PATH.parent / "make_sorting_analyzer.py"
    sa_command = f"conda run -n {SI_ENV} python {str(sa_script_path)} {str(ks_dir.parent)}"
    sa_status = subprocess.run([part.strip() for part in sa_command.split(" ")], capture_output=True, text=True)
    if sa_status.returncode==0:
        log("Sorting analyzer completed", p=session_name, r=ks_dir.name, c=70, n="sortinganalyzer", w=True)
        return 0
    else:
        log("Sorting analyzer failed", p=session_name, r=ks_dir.name, c=71, n="sortinganalyzer", w=True)
        return 71

def node_lfp(rec_dir: Path):
    """
    TODO: Implement.
    Codes 8X
    """
    return None