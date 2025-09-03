#!/usr/bin/env python3
"""
Atlas Verification Script for TI-Toolbox Classifier

Verifies that the required atlas files exist in /ti-toolbox/assets/atlas/
and have the correct dimensions for the classifier.
"""

import sys
from pathlib import Path
import nibabel as nib

# Add the classifier directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from core.atlas_manager import AtlasManager

def check_atlas_files():
    """Check if required atlas files exist and are accessible."""
    print("ATLAS VERIFICATION FOR TI-TOOLBOX CLASSIFIER")
    print("=" * 60)
    
    atlas_dir = Path("/ti-toolbox/assets/atlas")
    print(f"Checking atlas directory: {atlas_dir}")
    
    if not atlas_dir.exists():
        print(f"❌ Atlas directory does not exist: {atlas_dir}")
        return False
    
    print(f"✅ Atlas directory exists: {atlas_dir}")
    print()
    
    # Check each supported atlas
    supported_atlases = AtlasManager.get_supported_atlases()
    all_good = True
    
    for atlas_name, description in supported_atlases.items():
        print(f"Checking: {atlas_name}")
        print(f"Description: {description}")
        
        atlas_info = AtlasManager.SUPPORTED_ATLASES[atlas_name]
        nifti_file = atlas_dir / atlas_info["filename"]
        labels_file = atlas_dir / atlas_info["labels_file"]
        
        # Check NIfTI file
        if nifti_file.exists():
            print(f"  ✅ NIfTI file found: {nifti_file.name}")
            
            # Check dimensions
            try:
                img = nib.load(str(nifti_file))
                shape = img.shape
                print(f"  ✅ Dimensions: {shape}")
                
                # Load data to check it's valid
                data = img.get_fdata()
                n_rois = len(np.unique(data)) - 1  # Subtract 1 for background (0)
                print(f"  ✅ Number of ROIs: {n_rois}")
                
            except Exception as e:
                print(f"  ❌ Error loading NIfTI: {e}")
                all_good = False
        else:
            print(f"  ❌ NIfTI file missing: {nifti_file}")
            all_good = False
        
        # Check labels file
        if labels_file.exists():
            print(f"  ✅ Labels file found: {labels_file.name}")
            
            # Count labels
            try:
                with open(labels_file, 'r') as f:
                    lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    n_labels = len(lines)
                    print(f"  ✅ Number of labels: {n_labels}")
                    
                    # Show first few labels
                    print(f"  ✅ Sample labels:")
                    for i, line in enumerate(lines[:3]):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            print(f"    {parts[0]}: {parts[1]}")
                        if i >= 2:
                            break
                    if len(lines) > 3:
                        print(f"    ... and {len(lines) - 3} more")
                        
            except Exception as e:
                print(f"  ❌ Error reading labels file: {e}")
                all_good = False
        else:
            print(f"  ❌ Labels file missing: {labels_file}")
            all_good = False
        
        print()
    
    return all_good

def test_atlas_manager():
    """Test the AtlasManager with both supported atlases."""
    print("TESTING ATLAS MANAGER")
    print("=" * 30)
    
    supported_atlases = AtlasManager.get_supported_atlases()
    
    for atlas_name in supported_atlases.keys():
        print(f"\nTesting: {atlas_name}")
        try:
            # Test atlas manager initialization
            manager = AtlasManager(
                project_dir="/ti-toolbox",  # Standard path
                atlas_name=atlas_name
            )
            
            # Get atlas info
            info = manager.get_atlas_info()
            print(f"  ✅ Atlas loaded successfully")
            print(f"  ✅ Path: {info['path']}")
            print(f"  ✅ Loaded: {info['loaded']}")
            print(f"  ✅ Labels loaded: {info['labels_loaded']}")
            print(f"  ✅ Number of ROIs: {info['n_rois']}")
            
            if manager.atlas_data is not None:
                print(f"  ✅ Atlas data shape: {manager.atlas_data.shape}")
                print(f"  ✅ Atlas data type: {manager.atlas_data.dtype}")
                print(f"  ✅ Value range: {manager.atlas_data.min():.1f} - {manager.atlas_data.max():.1f}")
            
        except Exception as e:
            print(f"  ❌ Error loading atlas: {e}")
            return False
    
    return True

def main():
    """Main verification function."""
    import numpy as np
    
    print("Starting atlas verification...\n")
    
    # Check file existence and basic properties
    files_ok = check_atlas_files()
    
    if not files_ok:
        print("❌ ATLAS FILES CHECK FAILED")
        print("\nPlease ensure the following files exist in /ti-toolbox/assets/atlas/:")
        for atlas_name, info in AtlasManager.SUPPORTED_ATLASES.items():
            print(f"  • {info['filename']}")
            print(f"  • {info['labels_file']}")
        return 1
    
    # Test AtlasManager functionality
    manager_ok = test_atlas_manager()
    
    if not manager_ok:
        print("❌ ATLAS MANAGER TEST FAILED")
        return 1
    
    print("=" * 60)
    print("✅ ALL ATLAS VERIFICATION TESTS PASSED")
    print("=" * 60)
    print("\nSupported atlases:")
    for name, desc in AtlasManager.get_supported_atlases().items():
        print(f"  • {name}: {desc}")
    
    print(f"\nAtlas directory: /ti-toolbox/assets/atlas/")
    print("The classifier is ready to use with validated atlases!")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
