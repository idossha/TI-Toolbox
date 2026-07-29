"""
Input/Output utilities for neuroimaging data

This module contains functions for:
- Saving permutation logs
"""


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
