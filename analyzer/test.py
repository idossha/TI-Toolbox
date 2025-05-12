from mesh_analyzer import MeshAnalyzer

analyzer = MeshAnalyzer(
    mesh_path="/mnt/BIDS_new/derivatives/SimNIBS/sub-101/Simulations/L_Insula/TI/mesh/101_L_Insula_TI.msh",
    field_name="TI_max",
    subject_dir="/mnt/BIDS_new/derivatives/SimNIS/sub-101/m2m_101",
    output_dir="/mnt/BIDS_new/derivatives/SimNIS/sub-101/analysis_test"
)

# To analyze the whole head
results = analyzer.analyze_whole_head(atlas_type='HCP_MMP1', visualize=True)

# To analyze a specific cortical region
region_results = analyzer.analyze_cortex('HCP_MMP1', '35', visualize=True)

# To analyze a spherical region
sphere_results = analyzer.analyze_sphere([0, 0, 0], radius=10)