import pandas as pd
from pathlib import Path

# List of subject numbers as strings
subjects = [
    "109", "115", "119", "125", "127", "128", "129", "130", "131", "132", "133", "134", "136", "137", "139", "140", "141"
]

# Path to the reference file (sub-101)
ref_path = Path("sub-101/m2m_101/eeg_positions/GSN-HydroCel-185.csv")
ref_df = pd.read_csv(ref_path)

# Get the set of electrode labels (excluding fiducials)
ref_electrodes = set(ref_df[ref_df["Electrode"] == "Electrode"]["Label"])

for subj in subjects:
    subj_path = Path(f"sub-{subj}/m2m_{subj}/eeg_positions/GSN-HydroCel-185.csv")
    if not subj_path.exists():
        print(f"File not found: {subj_path}")
        continue

    df = pd.read_csv(subj_path)
    # Keep only rows where Label is in the reference set, or is a fiducial (optional)
    mask = df["Label"].isin(ref_electrodes) | df["Electrode"].str.contains("Fiducial", na=False)
    filtered_df = df[mask]
    # Overwrite the file (or save to a new file if you want to keep the original)
    filtered_df.to_csv(subj_path, index=False)
    print(f"Filtered {subj_path}: {len(df)} -> {len(filtered_df)} rows")

print("Done.")