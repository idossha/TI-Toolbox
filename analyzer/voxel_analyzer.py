import os
import numpy as np
import nibabel as nib
import subprocess
import tempfile
from pathlib import Path
import time
from visualizer import VoxelVisualizer


class VoxelAnalyzer:
    """
    A class for analyzing voxel-based data from medical imaging.
    """
    
    def __init__(self, field_nifti: str, field_name: str, subject_dir: str, output_dir: str):
        """
        Initialize the VoxelAnalyzer class.
        
        Args:
            field_nifti (str): Path to the NIfTI file containing field data
            field_name (str): Name of the field to analyze
            subject_dir (str): Directory containing subject data
            output_dir (str): Directory where analysis results will be saved
        """
        self.field_nifti = field_nifti
        self.field_name = field_name
        self.subject_dir = subject_dir
        self.output_dir = output_dir
        self.visualizer = VoxelVisualizer(output_dir)
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Validate that field_nifti exists
        if not os.path.exists(field_nifti):
            raise FileNotFoundError(f"Field file not found: {field_nifti}")

    def _extract_atlas_type(self, atlas_file):
        """
        Extract atlas type from filename by looking for common atlas names.
        
        Args:
            atlas_file (str): Path to the atlas file
            
        Returns:
            str: Atlas type if found, otherwise 'custom'
        """
        atlas_file = os.path.basename(atlas_file).lower()
        
        # Check for common atlas types in filename
        if 'dk40' in atlas_file:
            return 'DK40'
        elif 'hcp_mmp1' in atlas_file:
            return 'HCP_MMP1'
        elif 'a2009s' in atlas_file:
            return 'a2009s'
        else:
            return 'custom'

    def analyze_whole_head(self, atlas_file, visualize=False):
        """
        Analyze all regions in the specified atlas.
        
        Args:
            atlas_file (str): Path to the atlas file in NIfTI or MGZ format
            visualize (bool): Whether to generate visualizations
            
        Returns:
            dict: Dictionary mapping region names to their analysis results
        """
        start_time = time.time()
        print(f"Starting whole head analysis of atlas: {atlas_file}")
        
        # Extract atlas type from filename
        atlas_type = self._extract_atlas_type(atlas_file)
        print(f"Detected atlas type: {atlas_type}")
        
        try:
            # Load region information once
            region_info = self.get_atlas_regions(atlas_file)
            
            # Load atlas and field data once
            print(f"Loading atlas from {atlas_file}...")
            atlas_tuple = self.load_brain_image(atlas_file)
            atlas_img, atlas_arr = atlas_tuple
            
            print(f"Loading field from {self.field_nifti}...")
            field_tuple = self.load_brain_image(self.field_nifti)
            field_img, field_arr = field_tuple
            
            # Check if resampling is needed and do it once if necessary
            if atlas_arr.shape != field_arr.shape:
                print("Resampling atlas to match field dimensions...")
                atlas_img, atlas_arr = self.resample_to_match(
                    atlas_img,  
                    field_arr.shape,
                    field_img.affine
                )
                atlas_tuple = (atlas_img, atlas_arr)
            else:
                atlas_tuple = (atlas_img, atlas_arr)
            
            field_tuple = (field_img, field_arr)
            
            # Dictionary to store results for each region
            results = {}
            
            # Analyze each region in the atlas
            for region_id, info in region_info.items():
                region_name = info['name']
                try:
                    # Pass the pre-computed region_info and loaded data to avoid repeated loading
                    region_results = self.analyze_cortex(
                        atlas_file, 
                        region_id, 
                        region_info=region_info,
                        atlas_data=atlas_tuple,
                        field_data=field_tuple,
                        visualize=visualize  # Pass the visualize parameter
                    )
                    
                    # Only store the essential results, not the masks
                    results[region_name] = {
                        'mean_value': region_results['mean_value'],
                        'max_value': region_results['max_value'],
                        'min_value': region_results['min_value'],
                        'voxels_in_roi': region_results['voxels_in_roi']
                    }
                    
                except Exception as e:
                    print(f"Warning: Failed to analyze region {region_name}: {str(e)}")
                    results[region_name] = {
                        'mean_value': None,
                        'max_value': None,
                        'min_value': None,
                        'voxels_in_roi': 0
                    }
            
            # Print summary of results
            print("\nSummary of whole head analysis:")
            print(f"Total regions analyzed: {len(results)}")
            
            # Count regions with valid results
            valid_regions = sum(1 for r in results.values() if r['mean_value'] is not None)
            print(f"Regions with valid results: {valid_regions}")
            
            # Find regions with highest and lowest mean values
            valid_results = {name: res for name, res in results.items() if res['mean_value'] is not None}
            if valid_results:
                max_region = max(valid_results.items(), key=lambda x: x[1]['mean_value'])
                min_region = min(valid_results.items(), key=lambda x: x[1]['mean_value'])
                print(f"Region with highest mean value: {max_region[0]} ({max_region[1]['mean_value']:.6f})")
                print(f"Region with lowest mean value: {min_region[0]} ({min_region[1]['mean_value']:.6f})")
            
            # Generate scatter plot if visualization is requested
            if visualize:
                self.visualizer.generate_cortex_scatter_plot(results, atlas_type, data_type='voxel')
            
            # Calculate and print timing information
            end_time = time.time()
            total_time = end_time - start_time
            print(f"\nTiming Information:")
            print(f"Total analysis time: {total_time:.2f} seconds")
            print(f"Average time per region: {total_time/len(results):.2f} seconds")
            
            return results
            
        finally:
            # Clean up all temporary data
            try:
                del atlas_arr
                del field_arr
                del region_info
                if 'atlas_tuple' in locals():
                    del atlas_tuple
                if 'field_tuple' in locals():
                    del field_tuple
            except:
                pass

    def analyze_sphere(self, center_coordinates, radius):
        """
        Analyze a spherical region of interest from voxel data.
        
        Args:
            center_coordinates (list or tuple): [x, y, z] coordinates of sphere center in mm
            radius (float): Radius of the sphere in mm
            
        Returns:
            dict: Analysis results for the spherical region including:
                - mean_value: Mean field value in the ROI
                - max_value: Maximum field value in the ROI
                - min_value: Minimum field value in the ROI
                - roi_mask: Boolean mask of voxels in the ROI
        """
        print(f"Analyzing a spherical ROI (radius={radius}mm) at coordinates {center_coordinates}")
        
        # Load the NIfTI data
        img = nib.load(self.field_nifti)
        field_data = img.get_fdata()
        
        # Get voxel dimensions (for proper distance calculation)
        voxel_size = np.array(img.header.get_zooms()[:3])
        
        # Get affine transformation matrix
        affine = img.affine
        
        # Convert world coordinates to voxel coordinates if needed
        # This assumes center_coordinates are in world space
        # inv_affine = np.linalg.inv(affine)
        # voxel_coords = np.dot(inv_affine, np.append(center_coordinates, 1))[:3]
        
        # For simplicity, assume coordinates are already in voxel space
        voxel_coords = np.array(center_coordinates)
        
        # Create coordinate grids for the entire volume
        x_size, y_size, z_size = field_data.shape
        x, y, z = np.ogrid[:x_size, :y_size, :z_size]
        
        # Calculate distance from center voxel (using voxel dimensions to account for anisotropy)
        dist_from_center = np.sqrt(
            ((x - voxel_coords[0])**2 * voxel_size[0]**2) +
            ((y - voxel_coords[1])**2 * voxel_size[1]**2) +
            ((z - voxel_coords[2])**2 * voxel_size[2]**2)
        )
        
        # Create the spherical mask
        roi_mask = dist_from_center <= radius
        
        # Count voxels in ROI
        roi_voxels_count = np.sum(roi_mask)
        
        # Check if we have any voxels in the ROI
        if roi_voxels_count == 0:
            print("Warning: No voxels found in the specified ROI!")
            return {
                'mean_value': None,
                'max_value': None,
                'min_value': None,
                'roi_mask': roi_mask
            }
        
        # Get the field values within the ROI
        roi_values = field_data[roi_mask]
        
        # Calculate statistics
        min_value = np.min(roi_values)
        max_value = np.max(roi_values)
        mean_value = np.mean(roi_values)
        
        print(f"ROI Analysis Results:")
        print(f" Number of voxels in ROI: {roi_voxels_count}")
        print(f" Mean {self.field_name}: {mean_value:.6f}")
        print(f" Min {self.field_name}: {min_value:.6f}")
        print(f" Max {self.field_name}: {max_value:.6f}")
        
        # Return analysis results
        return {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'roi_mask': roi_mask,
            'voxels_in_roi': roi_voxels_count
        }

    def resample_to_match(self, source_img, target_shape, target_affine):
        """Resample source image to match target dimensions and affine using FreeSurfer's mri_convert.
        
        Parameters
        ----------
        source_img : nibabel.Nifti1Image
            Source image to resample
        target_shape : tuple
            Target shape (x, y, z)
        target_affine : numpy.ndarray
            Target affine transformation matrix
            
        Returns
        -------
        tuple
            (resampled nibabel image, resampled data array)
        """
        print(f"Resampling image from shape {source_img.shape} to {target_shape}")
        print("This may take a few moments...")
        
        # Create a temporary file for the target template
        with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_template:
            template_path = temp_template.name
        
        # Create a temporary file for the resampled output
        with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_output:
            output_path = temp_output.name
            
        try:
            # Save the source image to a temporary file
            with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_source:
                source_path = temp_source.name
                nib.save(source_img, source_path)
            
            # Create a template image with target dimensions
            template_img = nib.Nifti1Image(np.zeros(target_shape), target_affine)
            nib.save(template_img, template_path)
            
            # Run mri_convert to resample the image
            cmd = [
                'mri_convert',
                '--reslice_like', template_path,  # Use template for resampling
                source_path,                      # Source image
                output_path                       # Output image
            ]
            
            print(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True)
            
            # Load the resampled image
            resampled_img = nib.load(output_path)
            resampled_data = resampled_img.get_fdata()
            
            print("Resampling complete")
            return resampled_img, resampled_data
            
        finally:
            # Clean up temporary files
            for temp_file in [source_path, template_path, output_path]:
                try:
                    os.unlink(temp_file)
                except:
                    pass

    def analyze_cortex(self, atlas_file, target_region, region_info=None, atlas_data=None, field_data=None, visualize=False):
        """
        Analyze a field scan within a specific cortical region defined in an atlas.
        Only includes voxels with positive field values.
        
        Parameters
        ----------
        atlas_file : str
            Path to the atlas file in NIfTI or MGZ format
        target_region : str or int
            Name or ID of the target region to analyze
        region_info : dict, optional
            Pre-computed region information to avoid repeated mri_segstats calls
        atlas_data : tuple, optional
            Pre-loaded atlas data (atlas_img, atlas_data) to avoid repeated loading
        field_data : tuple, optional
            Pre-loaded field data (field_img, field_data) to avoid repeated loading
        visualize : bool, optional
            Whether to generate visualization files
            
        Returns
        -------
        dict
            Dictionary with region statistics
        """
        # Extract atlas type from filename
        atlas_type = self._extract_atlas_type(atlas_file)
        
        # Load the atlas and field data if not provided
        if atlas_data is None:
            print(f"Loading atlas from {atlas_file}...")
            atlas_tuple = self.load_brain_image(atlas_file)
            atlas_img, atlas_arr = atlas_tuple
        else:
            # Unpack the tuple
            atlas_img, atlas_arr = atlas_data
            
        if field_data is None:
            print(f"Loading field from {self.field_nifti}...")
            field_tuple = self.load_brain_image(self.field_nifti)
            field_img, field_arr = field_tuple
        else:
            # Unpack the tuple
            field_img, field_arr = field_data
        
        # Check file dimensions match
        if atlas_arr.shape != field_arr.shape:
            print("Warning: Atlas and field dimensions don't match, attempting to resample...")
            print(f"Atlas shape: {atlas_arr.shape}")
            print(f"Field shape: {field_arr.shape}")
        
            # Resample the atlas to match the field data
            atlas_img, atlas_arr = self.resample_to_match(
                atlas_img,
                field_arr.shape,
                field_img.affine
            )
            
            # Verify the resampling worked
            if atlas_arr.shape != field_arr.shape:
                raise ValueError(f"Failed to resample atlas to match field dimensions: {atlas_arr.shape} vs {field_arr.shape}")
        
        # Load region information if not provided
        if region_info is None:
            region_info = self.get_atlas_regions(atlas_file)
        
        # Determine region ID based on target_region
        print(f"Finding region information for {target_region}...")
        region_id, region_name = self.find_region(target_region, region_info)
        print(f"Analyzing region: {region_name} (ID: {region_id})")
        
        # Create mask for this region
        region_mask = (atlas_arr == region_id)  # Use the unpacked data array
        
        # Check if the mask contains any voxels
        mask_count = np.sum(region_mask)
        if mask_count == 0:
            print(f"Warning: Region {region_name} (ID: {region_id}) contains 0 voxels in the atlas")
            return {
                'mean_value': None,
                'max_value': None,
                'min_value': None,
                'roi_mask': region_mask,
                'voxels_in_roi': 0
            }
        
        # Filter for voxels with positive values
        value_mask = (field_arr > 0)  # Use the unpacked data array
        combined_mask = region_mask & value_mask
        
        # Extract field values after filtering
        field_values = field_arr[combined_mask]  # Use the unpacked data array
        
        # Check if any voxels remain after filtering
        filtered_count = len(field_values)
        if filtered_count == 0:
            print(f"Warning: Region {region_name} (ID: {region_id}) has no voxels with positive values")
            return {
                'mean_value': None,
                'max_value': None,
                'min_value': None,
                'roi_mask': combined_mask,
                'voxels_in_roi': 0
            }
        
        # Calculate statistics
        mean_value = np.mean(field_values)
        max_value = np.max(field_values)
        min_value = np.min(field_values)
        
        # Print summary of results
        print(f"Analysis Results for {region_name} (ID: {region_id}):")
        print(f"  Total voxels in region: {mask_count}")
        print(f"  Voxels with positive values: {filtered_count} ({filtered_count/mask_count*100:.2f}%)")
        print(f"  Mean field value: {mean_value:.6f}")
        print(f"  Max field value: {max_value:.6f}")
        print(f"  Min field value: {min_value:.6f}")
        
        # Generate visualization if requested
        if visualize:
            self.visualizer.generate_value_distribution_plot(
                field_values,
                region_name,
                atlas_type,
                mean_value,
                max_value,
                min_value,
                data_type='voxel'
            )
        
        # Return analysis results
        return {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'roi_mask': combined_mask,
            'voxels_in_roi': filtered_count
        }

    def get_atlas_regions(self, atlas_file):
        """Extract region information from atlas file using FreeSurfer's mri_segstats.
        
        Parameters
        ----------
        atlas_file : str
            Path to the atlas file (.nii or .mgz)
            
        Returns
        -------
        dict
            Dictionary mapping region IDs to region information
        """
        region_info = {}
        
        # Create temporary directory for output
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = os.path.join(temp_dir, "segstats.txt")
            
            # Run mri_segstats to get information about all segments in the atlas
            cmd = [
                'mri_segstats',
                '--seg', atlas_file,
                '--excludeid', '0',  # Exclude background
                '--ctab-default',    # Use default color table
                '--sum', output_file
            ]
            
            try:
                print(f"Running: {' '.join(cmd)}")
                subprocess.run(cmd, check=True, capture_output=True)
                
                # Parse the output file
                with open(output_file, 'r') as f:
                    # Skip header lines (all lines starting with #)
                    in_header = True
                    for line in f:
                        # Check if we've reached the end of the header
                        if in_header and not line.startswith('#'):
                            in_header = False
                            
                        # Process data lines (non-header)
                        if not in_header and line.strip():
                            parts = line.strip().split()
                            
                            # The format is:
                            # Index SegId NVoxels Volume_mm3 StructName
                            # We need at least 5 columns
                            if len(parts) >= 5:
                                try:
                                    region_id = int(parts[1])  # SegId is the second column
                                    n_voxels = int(parts[2])   # NVoxels is the third column
                                    
                                    # Structure name can contain spaces, so join the remaining parts
                                    region_name = ' '.join(parts[4:])
                                    
                                    # Generate a random color based on region_id for visualization
                                    # This creates a consistent color for each region
                                    import random
                                    random.seed(region_id)
                                    r = random.uniform(0.2, 0.8)
                                    g = random.uniform(0.2, 0.8)
                                    b = random.uniform(0.2, 0.8)
                                    
                                    region_info[region_id] = {
                                        'name': region_name,
                                        'voxel_count': n_voxels,
                                        'color': (r, g, b)
                                    }
                                except (ValueError, IndexError) as e:
                                    print(f"Warning: Could not parse line: {line.strip()}")
                                    print(f"Error: {str(e)}")
                    
                print(f"Found {len(region_info)} regions in atlas file")
                
            except subprocess.CalledProcessError as e:
                print(f"Warning: Could not extract region information using mri_segstats: {str(e)}")
                print(f"Command output: {e.stdout.decode() if e.stdout else ''}")
                print(f"Command error: {e.stderr.decode() if e.stderr else ''}")
                
        return region_info

    def load_brain_image(self, file_path):
        """Load brain image data from file, handling different formats.
        
        Parameters
        ----------
        file_path : str
            Path to the image file
            
        Returns
        -------
        tuple
            (nibabel image object, numpy array of data)
        """
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext == '.mgz':
            # Try to use nibabel directly first
            try:
                img = nib.load(file_path)
                data = img.get_fdata()
                return img, data
            except Exception as e:
                print(f"Could not load MGZ file directly: {str(e)}")
                
                # Try to convert MGZ to NIfTI using mri_convert
                try:
                    # Create a temporary file for the converted image
                    with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp:
                        temp_path = temp.name
                    
                    # Run mri_convert to convert MGZ to NIfTI
                    cmd = ['mri_convert', file_path, temp_path]
                    subprocess.run(cmd, check=True)
                    
                    # Load the converted file
                    img = nib.load(temp_path)
                    data = img.get_fdata()
                    
                    # Clean up
                    os.unlink(temp_path)
                    
                    return img, data
                except Exception as e2:
                    raise RuntimeError(f"Failed to convert MGZ file: {str(e2)}")
        else:
            # For NIfTI and other formats, use nibabel directly
            img = nib.load(file_path)
            data = img.get_fdata()
            return img, data
        
    def find_region(self, target_region, region_info):
        """Find region ID and name based on input.
        
        Parameters
        ----------
        target_region : str or int
            Target region name or ID
        region_info : dict
            Dictionary with region information
            
        Returns
        -------
        tuple
            (region_id, region_name)
        """
        # Check if target_region is an ID (int) or can be converted to one
        try:
            region_id = int(target_region)
            # If it's an ID, get the name from region_info if available
            if region_info and region_id in region_info:
                region_name = region_info[region_id]['name']
            else:
                region_name = f"Region {region_id}"
            return region_id, region_name
        except ValueError:
            # target_region is a string name, need to find the corresponding ID
            if not region_info:
                raise ValueError("Region labels are required to look up regions by name")
            
            # Search for the region name (case-insensitive)
            target_lower = target_region.lower()
            for region_id, info in region_info.items():
                if target_lower in info['name'].lower():
                    return region_id, info['name']
            
            # If we get here, region name was not found
            raise ValueError(f"Region name '{target_region}' not found in region labels")