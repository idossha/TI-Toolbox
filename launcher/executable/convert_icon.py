#!/usr/bin/env python3
"""
Icon Converter for TI-Toolbox
Converts icon.png to .ico (Windows) and .icns (macOS) formats
"""

import os
import sys
import platform

# Try to import PIL with graceful fallback
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: PIL/Pillow not available. Install with: pip install Pillow")

def convert_png_to_ico(png_path, ico_path):
    """Convert PNG to ICO format for Windows"""
    if not PIL_AVAILABLE:
        print("ERROR: Cannot convert to ICO: Pillow not installed")
        return False
        
    try:
        # Open the PNG image
        img = Image.open(png_path)
        
        # ICO format supports multiple sizes, so we'll create common sizes
        # Windows typically uses 16x16, 32x32, 48x48, 64x64, 128x128, 256x256
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        
        # Create a list of images at different sizes
        images = []
        for size in sizes:
            resized = img.resize(size, Image.Resampling.LANCZOS)
            images.append(resized)
        
        # Save as ICO with multiple sizes
        images[0].save(ico_path, format='ICO', sizes=[img.size for img in images])
        print(f"SUCCESS: Created Windows icon: {ico_path}")
        return True
        
    except Exception as e:
        print(f"ERROR: Error creating ICO: {e}")
        return False

def convert_png_to_icns(png_path, icns_path):
    """Convert PNG to ICNS format for macOS"""
    if not PIL_AVAILABLE:
        print("ERROR: Cannot convert to ICNS: Pillow not installed")
        return False
        
    try:
        # For ICNS, we need to create temporary PNG files at specific sizes
        # and use the iconutil command (macOS only)
        
        if platform.system() != "Darwin":
            print("WARNING: ICNS conversion requires macOS. Skipping...")
            return False
            
        # Create iconset directory
        iconset_dir = "TI-Toolbox.iconset"
        if os.path.exists(iconset_dir):
            import shutil
            shutil.rmtree(iconset_dir)
        os.makedirs(iconset_dir)
        
        # Open original image
        img = Image.open(png_path)
        
        # ICNS requires specific sizes and naming
        icns_sizes = [
            (16, "icon_16x16.png"),
            (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"),
            (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"),
            (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"),
            (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"),
            (1024, "icon_512x512@2x.png"),
        ]
        
        # Create all required sizes
        for size, filename in icns_sizes:
            resized = img.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(os.path.join(iconset_dir, filename))
        
        # Use iconutil to create ICNS
        import subprocess
        result = subprocess.run([
            'iconutil', '-c', 'icns', iconset_dir, '-o', icns_path
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"SUCCESS: Created macOS icon: {icns_path}")
            # Clean up iconset directory
            import shutil
            shutil.rmtree(iconset_dir)
            return True
        else:
            print(f"ERROR: Error creating ICNS: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"ERROR: Error creating ICNS: {e}")
        return False

def main():
    """Main conversion function"""
    png_path = "icon.png"
    ico_path = "icon.ico"
    icns_path = "icon.icns"
    
    print("Converting icon.png to executable formats...")
    print()
    
    # Check if PNG exists
    if not os.path.exists(png_path):
        print(f"ERROR: {png_path} not found!")
        print("WARNING: Building without custom icon (will use default)")
        return True  # Not a critical error
    
    if not PIL_AVAILABLE:
        print("ERROR: Pillow not installed. Cannot convert icons.")
        print("INFO: Install with: pip install Pillow")
        print("WARNING: Building without custom icon (will use default)")
        return True  # Not a critical error
    
    success = True
    
    # Convert to ICO (Windows)
    print("Converting to ICO format (Windows)...")
    if not convert_png_to_ico(png_path, ico_path):
        success = False
    
    print()
    
    # Convert to ICNS (macOS)
    print("Converting to ICNS format (macOS)...")
    if not convert_png_to_icns(png_path, icns_path):
        success = False
    
    print()
    
    if success:
        print("SUCCESS: Icon conversion completed!")
        print()
        print("Files created:")
        if os.path.exists(ico_path):
            print(f"  * {ico_path} (Windows)")
        if os.path.exists(icns_path):
            print(f"  * {icns_path} (macOS)")
        print()
        print("The PyInstaller spec file will be updated to use these icons.")
    else:
        print("WARNING: Some icon conversions failed. Building with default icon.")
    
    return True  # Always return True so build continues

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 