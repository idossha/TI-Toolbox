"""
Input/Output utilities for neuroimaging data

This module contains functions for:
- Loading and saving NIfTI files
- Reading subject data from CSV
- Saving permutation logs
"""

import numpy as np
import pandas as pd
import nibabel as nib

import os


def load_subject_data(csv_file, data_dir, return_ids=False):
    """
    Load subject classifications and corresponding NIfTI files

    Parameters:
    -----------
    csv_file : str
        Path to CSV file with columns: subject_id, response, simulation_name
    data_dir : str
        Directory containing NIfTI files
    return_ids : bool
        If True, also return subject IDs

    Returns:
    --------
    responders : ndarray (x, y, z, n_subjects)
        4D array of responder data
    non_responders : ndarray (x, y, z, n_subjects)
        4D array of non-responder data
    template_img : nibabel image
        Template image for affine/header information
    responder_ids : list (only if return_ids=True)
        List of responder subject IDs
    non_responder_ids : list (only if return_ids=True)
        List of non-responder subject IDs
    """
    df = pd.read_csv(csv_file)

    responders = []
    non_responders = []
    responder_ids = []
    non_responder_ids = []

    for _, row in df.iterrows():
        subject_num = row["subject_id"].replace("sub-", "")
        sim_name = row["simulation_name"]
        response = row["response"]

        # Construct filename
        filename = f"{subject_num}_grey_{sim_name}_TI_MNI_MNI_TI_max.nii.gz"
        filepath = os.path.join(data_dir, filename)

        if not os.path.exists(filepath):
            print(f"Warning: File not found - {filename}")
            continue

        # Load NIfTI
        img = nib.load(filepath)
        data = img.get_fdata()

        # Ensure 3D data (squeeze out extra dimensions if present)
        while data.ndim > 3:
            data = np.squeeze(data, axis=-1)

        if response == 1:
            responders.append(data)
            responder_ids.append(subject_num)
        else:
            non_responders.append(data)
            non_responder_ids.append(subject_num)

    print(f"\nLoaded {len(responders)} responders: {responder_ids}")
    print(f"Loaded {len(non_responders)} non-responders: {non_responder_ids}")

    # Stack into 4D arrays (subjects x volume)
    responders = np.stack(responders, axis=-1)
    non_responders = np.stack(non_responders, axis=-1)

    print(f"Responders shape: {responders.shape}")
    print(f"Non-responders shape: {non_responders.shape}")

    if return_ids:
        return responders, non_responders, img, responder_ids, non_responder_ids
    else:
        return responders, non_responders, img


def save_nifti(data, affine, header, filepath, dtype=np.float32):
    """
    Save data as NIfTI file

    Parameters:
    -----------
    data : ndarray
        Data to save
    affine : ndarray
        Affine transformation matrix
    header : nibabel header
        NIfTI header
    filepath : str
        Output file path
    dtype : numpy dtype
        Data type for output
    """
    img = nib.Nifti1Image(data.astype(dtype), affine, header)
    nib.save(img, filepath)
    print(f"Saved: {filepath}")


def save_permutation_details(
    permutation_info, output_file, subject_ids_resp, subject_ids_non_resp
):
    """
    Save detailed information about each permutation to a file

    Parameters:
    -----------
    permutation_info : list of dict
        List containing permutation details with keys:
        - 'perm_num': permutation number
        - 'perm_idx': permutation indices
        - 'max_cluster_size': maximum cluster statistic found (size or mass)
    output_file : str
        Path to output file
    subject_ids_resp : list
        Original responder subject IDs
    subject_ids_non_resp : list
        Original non-responder subject IDs
    """
    all_subject_ids = subject_ids_resp + subject_ids_non_resp
    n_resp = len(subject_ids_resp)

    with open(output_file, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("PERMUTATION TEST DETAILS\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total permutations: {len(permutation_info)}\n")
        f.write(f"Original Responders (n={n_resp}): {subject_ids_resp}\n")
        f.write(
            f"Original Non-Responders (n={len(subject_ids_non_resp)}): {subject_ids_non_resp}\n"
        )
        f.write("\n" + "=" * 80 + "\n\n")

        for info in permutation_info:
            perm_num = info["perm_num"]
            perm_idx = info["perm_idx"]
            max_stat = info["max_cluster_size"]

            # Get permuted groups
            perm_resp_ids = [all_subject_ids[i] for i in perm_idx[:n_resp]]
            perm_non_resp_ids = [all_subject_ids[i] for i in perm_idx[n_resp:]]

            f.write(f"Permutation {perm_num:4d}: ")
            f.write(f"Responders: {perm_resp_ids}, ")
            f.write(f"Non-Responders: {perm_non_resp_ids}, ")
            # Format as float to handle both size (int) and mass (float)
            if isinstance(max_stat, float):
                f.write(f"Max Cluster Stat: {max_stat:10.2f}\n")
            else:
                f.write(f"Max Cluster Stat: {max_stat:10d}\n")

    print(f"Saved permutation details to: {output_file}")
