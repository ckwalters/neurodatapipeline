import neurodatapipeline as ndp

def main():
    """
    Run Neuropixels SpikeGLX recording data processing pipeline.
    Available nodes: ["catgt", "tprime", "kilosort", "sa"]
    """

    # Organize raw SGLX recordings into session-level folder structure
    ndp.organize_new_sessions("example_session")
    
    # Run pipeline
    ndp.run_pipeline(search_all=True, search_key="example_session", nodes=["catgt", "tprime", "kilosort"])

    # Search for sessions that need data curation
    print(ndp.find_sessions(search_dict={"kilosort_bool":True,"phy_bool":False}))

if __name__=="__main__":
    main()