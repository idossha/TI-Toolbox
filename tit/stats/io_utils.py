"""
Input/Output utilities for neuroimaging data

This module contains functions for:
- Saving permutation logs (group comparison and correlation)
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
            f.write(f"Max Cluster Stat: {_format_stat(max_stat)}\n")


def save_correlation_permutation_details(permutation_info, output_file, subject_ids):
    """Save each correlation permutation's effect-size shuffle to a file.

    In permutation ``k`` subject ``subject_ids[j]`` is given the effect size of
    ``subject_ids[perm_idx[j]]``; each line lists those donors in subject order.
    ``permutation_info`` has the keys :func:`save_permutation_details` documents.
    """
    with open(output_file, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("PERMUTATION TEST DETAILS (CORRELATION)\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total permutations: {len(permutation_info)}\n")
        f.write(f"Subjects (n={len(subject_ids)}): {subject_ids}\n")
        f.write(
            "Each line names, in subject order, whose effect size each subject got.\n"
        )
        f.write("\n" + "=" * 80 + "\n\n")

        for info in permutation_info:
            donors = [subject_ids[i] for i in info["perm_idx"]]
            f.write(f"Permutation {info['perm_num']:4d}: ")
            f.write(f"Effect sizes from: {donors}, ")
            f.write(f"Max Cluster Stat: {_format_stat(info['max_cluster_size'])}\n")


def _format_stat(max_stat) -> str:
    """Cluster mass is a float, cluster size an integer."""
    if isinstance(max_stat, float):
        return f"{max_stat:10.2f}"
    return f"{max_stat:10d}"
