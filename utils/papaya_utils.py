#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility functions for integrating Papaya 3D neuroimaging viewer with TI field reports.
"""

import os
import shutil
from pathlib import Path

def get_papaya_dir():
    """Get the path to the Papaya directory."""
    # Try different possible locations
    possible_locations = [
        Path(__file__).parent.parent / "Papaya",  # Project root
        Path(__file__).parent / "Papaya",         # Utils directory
        Path.cwd() / "Papaya",                    # Current working directory
        Path("/development/Papaya"),              # Docker container location
        Path("/root/Papaya"),                     # Root directory location
    ]
    
    for location in possible_locations:
        if (location / "papaya-builder.sh").exists():
            return location
    
    return None

def get_papaya_viewer_html(t1_file, overlay_file, report_dir):
    """
    Generate embeddable HTML for a Papaya viewer.
    
    Parameters
    ----------
    t1_file : str
        Path to T1 reference NIfTI file
    overlay_file : str
        Path to field NIfTI file to visualize
    report_dir : str
        Directory where the report will be saved (for relative paths)
        
    Returns
    -------
    str
        HTML content for the Papaya viewer, or fallback message if not available
    """
    try:
        # Find Papaya directory
        papaya_dir = get_papaya_dir()
        if not papaya_dir:
            return _generate_papaya_fallback_html(t1_file, overlay_file)
        
        # Check if files exist
        if not os.path.exists(t1_file) or not os.path.exists(overlay_file):
            return _generate_papaya_fallback_html(t1_file, overlay_file, "Files not found")
        
        # Get relative paths for the data files
        t1_rel = os.path.relpath(os.path.abspath(t1_file), report_dir)
        overlay_rel = os.path.relpath(os.path.abspath(overlay_file), report_dir)
        
        # Copy Papaya resources
        success = _copy_papaya_resources(papaya_dir, report_dir)
        if not success:
            return _generate_papaya_fallback_html(t1_file, overlay_file, "Could not copy Papaya resources")
        
        # Generate unique IDs for this viewer to avoid conflicts
        viewer_id = abs(hash(f"{t1_file}_{overlay_file}")) % 10000
        
        # Generate viewer HTML
        viewer_html = f"""
        <div class="papaya-viewer-container" style="margin: 20px 0; border: 2px solid #dee2e6; border-radius: 8px; background: white;">
            <!-- Load buttons -->
            <div style="padding: 15px; background: #f8f9fa; border-bottom: 1px solid #dee2e6; text-align: center;">
                <button onclick="loadT1_{viewer_id}()" style="margin: 5px; padding: 10px 20px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">
                    📱 Load T1 Reference
                </button>
                <button onclick="loadTI_{viewer_id}()" style="margin: 5px; padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">
                    🧠 Load TI Field
                </button>
                <button onclick="resetViewer_{viewer_id}()" style="margin: 5px; padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">
                    🔄 Reset
                </button>
            </div>
            
            <!-- Papaya viewer container -->
            <div class="papaya" id="papaya_{viewer_id}" style="width: 100%; height: 500px;"></div>
            
            <!-- Instructions -->
            <div style="padding: 15px; background: #e3f2fd; border-top: 1px solid #dee2e6;">
                <h5 style="margin-top: 0; color: #1976d2;">🎮 Viewer Controls:</h5>
                <ul style="margin: 5px 0; color: #1976d2; font-size: 14px;">
                    <li><strong>Mouse wheel:</strong> Zoom in/out</li>
                    <li><strong>Left click + drag:</strong> Pan around</li>
                    <li><strong>Keyboard arrows:</strong> Navigate through slices</li>
                </ul>
            </div>
        </div>
        
        <!-- Papaya viewer scripts -->
        <script type="text/javascript">
            // Viewer for {os.path.basename(t1_file)}
            var papayaViewer_{viewer_id} = null;
            
            document.addEventListener('DOMContentLoaded', function() {{
                // Initialize this specific viewer
                setTimeout(function() {{
                    if (typeof papaya !== 'undefined') {{
                        // Initialize viewer for this container
                        var container = document.getElementById('papaya_{viewer_id}');
                        if (container) {{
                            papaya.Container.addViewer(container, {{}});
                            
                            setTimeout(function() {{
                                var containers = papaya.Container.getAllContainers();
                                for (var i = 0; i < containers.length; i++) {{
                                    if (containers[i].containerHtml === container) {{
                                        papayaViewer_{viewer_id} = containers[i];
                                        console.log('Papaya viewer initialized for {os.path.basename(t1_file)}');
                                        break;
                                    }}
                                }}
                            }}, 500);
                        }}
                    }}
                }}, 1000);
            }});
            
            // Load T1 image
            function loadT1_{viewer_id}() {{
                if (!papayaViewer_{viewer_id}) {{
                    alert('Viewer not ready yet. Please wait a moment and try again.');
                    return;
                }}
                
                papayaViewer_{viewer_id}.loadImage(["{t1_rel}"], {{}}, function() {{
                    console.log('T1 loaded successfully');
                }});
            }}
            
            // Load TI field image
            function loadTI_{viewer_id}() {{
                if (!papayaViewer_{viewer_id}) {{
                    alert('Viewer not ready yet. Please wait a moment and try again.');
                    return;
                }}
                
                papayaViewer_{viewer_id}.loadImage(["{overlay_rel}"], {{}}, function() {{
                    console.log('TI field loaded successfully');
                }});
            }}
            
            // Reset viewer
            function resetViewer_{viewer_id}() {{
                if (!papayaViewer_{viewer_id}) {{
                    alert('Viewer not ready yet.');
                    return;
                }}
                
                papayaViewer_{viewer_id}.resetViewer();
                console.log('Viewer reset');
            }}
        </script>
        """
        
        return viewer_html
        
    except Exception as e:
        return _generate_papaya_fallback_html(t1_file, overlay_file, f"Error: {str(e)}")

def _copy_papaya_resources(papaya_dir, report_dir):
    """Copy Papaya JS and CSS resources to the report directory."""
    try:
        # Copy Papaya resources from standard release
        papaya_release = papaya_dir / "release" / "current" / "standard"
        if not papaya_release.exists():
            print(f"WARNING: Could not find Papaya release directory at {papaya_release}")
            return False
            
        # Copy JS and CSS files
        for file in ["papaya.js", "papaya.css"]:
            src = papaya_release / file
            if not src.exists():
                print(f"WARNING: Could not find {file} in {papaya_release}")
                return False
            dst = Path(report_dir) / file
            # Only copy if file doesn't exist or is older
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)
                print(f"Copied {src} to {dst}")
        
        return True
    except Exception as e:
        print(f"WARNING: Failed to copy Papaya resources: {str(e)}")
        return False

def _generate_papaya_fallback_html(t1_file, overlay_file, error_msg="Papaya viewer not available"):
    """Generate fallback HTML when Papaya is not available."""
    t1_name = os.path.basename(t1_file)
    overlay_name = os.path.basename(overlay_file)
    
    return f"""
    <div class="papaya-fallback" style="margin: 15px 0; border: 2px dashed #6c757d; border-radius: 8px; padding: 20px; text-align: center; background: #f8f9fa;">
        <div style="font-size: 18px; margin-bottom: 10px;">🧠</div>
        <h6 style="color: #495057; margin-bottom: 10px;">Interactive Papaya Viewer</h6>
        <p style="color: #6c757d; margin-bottom: 15px;">
            <strong>T1:</strong> {t1_name}<br>
            <strong>TI Field:</strong> {overlay_name}
        </p>
        
        <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 12px; border-radius: 6px; margin-bottom: 15px;">
            <p style="color: #856404; margin: 0; font-size: 14px;">
                <strong>⚠️ {error_msg}</strong><br>
                To enable interactive visualization, install Papaya:
            </p>
        </div>
        
        <div style="background-color: #e8f5e8; padding: 12px; border-radius: 6px; margin-bottom: 15px;">
            <p style="color: #2e7d32; margin: 0; font-size: 14px;">
                💡 <strong>To install Papaya:</strong><br>
                1. <code style="background: #333; color: #0f0; padding: 2px 4px;">git clone https://github.com/rii-mango/Papaya.git</code><br>
                2. Place in project root directory<br>
                3. Regenerate report for interactive features!
            </p>
        </div>
        
        <div style="margin-top: 15px;">
            <button onclick="window.open('https://github.com/rii-mango/Papaya', '_blank')" 
                    style="background-color: #2196f3; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-right: 10px; font-size: 12px;">
                🌐 Learn About Papaya
            </button>
            <button onclick="copyToClipboard('{t1_file}')" 
                    style="background-color: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 12px;">
                📋 Copy T1 Path
            </button>
        </div>
    </div>
    """

def ensure_papaya_resources_in_report(report_dir):
    """Ensure Papaya resources are available in the report directory."""
    try:
        papaya_dir = get_papaya_dir()
        if not papaya_dir:
            return False
        
        return _copy_papaya_resources(papaya_dir, report_dir)
    except Exception as e:
        print(f"WARNING: Failed to ensure Papaya resources: {str(e)}")
        return False

# Legacy function for backward compatibility
def add_papaya_viewer(html_path, t1_file, overlay_file):
    """
    Legacy function - adds Papaya viewer to an existing HTML file.
    For new code, use get_papaya_viewer_html() instead.
    """
    report_dir = os.path.dirname(os.path.abspath(html_path))
    
    try:
        # Generate viewer HTML
        viewer_html = get_papaya_viewer_html(t1_file, overlay_file, report_dir)
        
        # Read the HTML file
        with open(html_path, 'r') as f:
            html_content = f.read()
        
        # Add Papaya CSS/JS includes if not present
        if 'papaya.css' not in html_content:
            css_link = '<link rel="stylesheet" type="text/css" href="papaya.css" />'
            if '<head>' in html_content:
                html_content = html_content.replace('<head>', f'<head>\n{css_link}')
            else:
                viewer_html = css_link + viewer_html
        
        if 'papaya.js' not in html_content:
            js_script = '<script type="text/javascript" src="papaya.js"></script>'
            if '<head>' in html_content:
                html_content = html_content.replace('<head>', f'<head>\n{js_script}')
            else:
                viewer_html = js_script + viewer_html
        
        # Insert the viewer HTML
        if "</body>" in html_content:
            html_content = html_content.replace("</body>", f"{viewer_html}</body>")
        else:
            html_content += f"\n{viewer_html}\n"
        
        # Write back to file
        with open(html_path, 'w') as f:
            f.write(html_content)
        
        print(f"Successfully added Papaya viewer to report: {html_path}")
        return True
        
    except Exception as e:
        print(f"WARNING: Failed to add Papaya viewer: {str(e)}")
        return False