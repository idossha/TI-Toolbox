import numpy as np


def find_sphere_element_indices(mesh, roi_coords, radius=3.0):
    """
    Find mesh element indices within spherical ROI
    
    Args:
        mesh: SimNIBS mesh object
        roi_coords: [x, y, z] center coordinates of ROI
        radius: Radius in mm for spherical ROI
    
    Returns:
        roi_indices: Array of element indices within radius
        element_volumes: Array of element volumes for weighted averaging
    """
    # Get element centers (tetrahedra baricenters)
    element_centers = mesh.elements_baricenters()
    
    # Calculate distances from ROI center to each element
    distances = np.sqrt(
        (element_centers[:, 0] - roi_coords[0])**2 +
        (element_centers[:, 1] - roi_coords[1])**2 +
        (element_centers[:, 2] - roi_coords[2])**2
    )
    
    # Find elements within ROI
    roi_mask = distances <= radius
    roi_indices = np.where(roi_mask)[0]
    
    # Get element volumes for weighted averaging
    element_volumes = mesh.elements_volumes_and_areas()[roi_mask]
    
    return roi_indices, element_volumes


def find_grey_matter_indices(mesh, grey_matter_tags=[2]):
    """
    Find mesh element indices in grey matter
    
    Args:
        mesh: SimNIBS mesh object
        grey_matter_tags: List of tissue tags for grey matter (default: [2] for GM)
    
    Returns:
        gm_indices: Array of element indices in grey matter
        gm_volumes: Array of element volumes for weighted averaging
    """
    # Get element tags
    element_tags = mesh.elm.tag1
    
    # Find elements in grey matter
    gm_mask = np.isin(element_tags, grey_matter_tags)
    gm_indices = np.where(gm_mask)[0]
    
    # Get element volumes
    gm_volumes = mesh.elements_volumes_and_areas()[gm_mask]
    
    return gm_indices, gm_volumes



def calculate_roi_metrics(ti_field_roi, element_volumes, ti_field_gm=None, gm_volumes=None):
    """
    Calculate ROI metrics from TI field values
    
    Args:
        ti_field_roi: TI field values within ROI [n_roi_elements]
        element_volumes: Element volumes for weighted averaging [n_roi_elements]
        ti_field_gm: Optional TI field values in grey matter [n_gm_elements]
        gm_volumes: Optional grey matter element volumes [n_gm_elements]
    
    Returns:
        dict: Dictionary with TImax_ROI, TImean_ROI, n_elements, and optionally Focality
    """
    if len(ti_field_roi) == 0:
        return {
            'TImax_ROI': 0.0,
            'TImean_ROI': 0.0,
            'n_elements': 0,
            'Focality': 0.0
        }
    
    # Maximum field in ROI
    timax_roi = float(np.max(ti_field_roi))
    
    # Volume-weighted mean field in ROI
    timean_roi = float(np.average(ti_field_roi, weights=element_volumes))
    
    # Calculate focality if grey matter data provided
    focality = None
    if ti_field_gm is not None and gm_volumes is not None and len(ti_field_gm) > 0:
        # Volume-weighted mean in grey matter
        timean_gm = float(np.average(ti_field_gm, weights=gm_volumes))
        
        # Focality = TImean_ROI / TImean_GM (higher = more focal)
        if timean_gm > 0:
            focality = float(timean_roi / timean_gm)
        else:
            focality = 0.0
    
    result = {
        'TImax_ROI': timax_roi,
        'TImean_ROI': timean_roi,
        'n_elements': int(len(ti_field_roi))
    }
    
    if focality is not None:
        result['Focality'] = focality
        result['TImean_GM'] = timean_gm
    
    return result
