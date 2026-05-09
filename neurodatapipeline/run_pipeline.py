import time
import tkinter as tk
import tkinter.font as font
from threading import Thread
from .config import *
from .pipeline_nodes import pipeline
from .session_state_log import search_sessions, update_session_states
from .pipeline_io import check_disk_space, log


# Globals
stop = False
stopped = False


def run_pipeline(search_all=False, search_key="", nodes=None):
    """
    Run neurodata processing and spike sorting pipeline.
    Current node options (run in order, do not omit earlier nodes):
        ["catgt", "tprime", "kilosort", "sa"]
    """
    # Find sessions
    session_paths = search_sessions(search_all, search_key, nodes, mode="any")
    
    # Run pipeline on each session path
    pipeline_loop(session_paths, nodes)
    
    # Update session log
    update_session_states()


def pipeline_loop(session_paths: list, nodes=None):
    """
    Main loop for running pipeline on each session with button to end gracefully
    after current session is completed. Codes: 9X
    Parameters:
        session_paths (list): list of Path objs
        nodes (list): list of pipeline node keys
    """
    if session_paths is None:
        log("No sessions found")
        return

    log("Starting pipeline", c=90, n="pipeline_loop", w=True)

    # Button interface
    global stop
    global stopped
    t1 = Thread(target=StopButton)
    t1.start()

    # Loop through found sessions
    for session_path in session_paths:
        # Run pipeline on session
        tic = time.time()
        pipeline(session_path, nodes=nodes)
        log(f"{(time.time()-tic)/60:.0f} minutes", session_path.name)

        # Running low on disk space?
        if not check_disk_space():
            log("Stopping: running low on disk space", c=93, n="pipeline_loop", w=True)
            stopped = True
            break

        # Stop button pressed
        if stop:
            log("Stopping: manual stop", c=92, n="pipeline_loop", w=True)
            stopped = True
            break

    # All sessions completed
    if not stopped:
        log("Completed running on all sessions", c=90, n="pipeline_loop", w=True)
    stopped = True


class StopButton:
    """GUI element to stop pipeline."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry("300x200")
        self.root.title("Sorting Pipeline")
        my_font = font.Font(size=16)
        self.button = tk.Button(
            master=self.root,
            text="Stop After Current Session",
            font=my_font,
            width=40,
            height=12,
            bg="white",
            fg="black",
            command=self.stop)
        self.button.pack()
        self._job = self.root.after(1000, self.check_continue)
        self.root.mainloop()

    def stop(self):
        global stop
        stop = True
        self.button["text"] = "Will Stop After Current Session"

    def check_continue(self):
        global stopped
        if stopped:
            if self._job is not None:
                self.root.after_cancel(self._job)
                self._job = None
            self.root.destroy()
        else:
            self._job = self.root.after(1000, self.check_continue)