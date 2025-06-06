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

def create_papaya_viewer(report_dir, viewer_name, t1_file, field_files, labels=None):
    """
    Create a simple, empty Papaya viewer with shared resources.
    
    Parameters
    ----------
    report_dir : str
        Directory where the report will be saved
    viewer_name : str
        Name for this viewer (used for file naming)
    t1_file : str
        Path to T1 reference NIfTI file
    field_files : list
        List of field NIfTI files to include
    labels : list, optional
        List of labels for each field file
        
    Returns
    -------
    str
        HTML content for embedding the viewer, or error message
    """
    try:
        # Find Papaya directory
        papaya_dir = get_papaya_dir()
        if not papaya_dir:
            return _generate_papaya_installation_guide(field_files[0] if field_files else "")
        
        # Ensure all files exist
        all_files = [t1_file] + field_files
        for file_path in all_files:
            if not os.path.exists(file_path):
                return f"""
                <div style="margin: 15px 0; padding: 15px; background-color: #fff3cd; border-radius: 8px; border: 1px solid #ffeaa7;">
                    <h6 style="color: #856404; margin-bottom: 10px;">⚠️ File Not Found</h6>
                    <p style="color: #856404; margin: 0; font-size: 14px;">
                        <strong>Missing file:</strong> {os.path.basename(file_path)}<br>
                        <strong>Path:</strong> {file_path}
                    </p>
                </div>
                """
        
        # Copy shared Papaya resources to report directory (only once)
        papaya_release = papaya_dir / "release" / "current" / "standard"
        if not papaya_release.exists():
            return _generate_papaya_error_message(viewer_name, f"Papaya release directory not found at {papaya_release}")
        
        # Copy JS and CSS files to shared location
        essential_files = ["papaya.js", "papaya.css"]
        for file in essential_files:
            src = papaya_release / file
            if not src.exists():
                return _generate_papaya_error_message(viewer_name, f"Missing Papaya file: {file}")
            dst = Path(report_dir) / file
            # Only copy if file doesn't exist or is older
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)
                print(f"Copied shared Papaya resource: {src} to {dst}")
        
        # Generate labels if not provided
        if not labels:
            labels = ["T1 Reference"] + [f"TI Field {i+1}" for i in range(len(field_files))]
        else:
            labels = ["T1 Reference"] + labels
        
        # Create the HTML for direct embedding in the main report
        html_content = f"""
        <!-- Papaya Viewer for {viewer_name} -->
        <div style="margin: 20px 0; border: 2px solid #dee2e6; border-radius: 8px; background: white;">
            <div style="padding: 20px; font-family: Arial, sans-serif;">
                <h4 style="margin: 0 0 15px 0; color: #495057;">🧠 Interactive Brain Viewer - {viewer_name}</h4>
                
                <div style="background-color: #f8f9fa; padding: 12px; border-radius: 6px; margin-bottom: 20px; border: 1px solid #dee2e6;">
                    <h5 style="color: #495057; margin: 0 0 8px 0; font-size: 14px;">📋 Available Files:</h5>
                    <ul style="margin: 5px 0; color: #6c757d; font-size: 13px; padding-left: 20px;">
                        <li>📷 <strong>T1 Reference:</strong> {os.path.basename(t1_file)}</li>
                        {_generate_available_files_list(field_files, labels[1:])}
                    </ul>
                </div>
                
                <!-- Direct Papaya viewer -->
                <div class="papaya" id="papaya_{viewer_name}" data-params="params_{viewer_name}" style="width: 100%; height: 500px; border: 1px solid #ddd; border-radius: 4px;"></div>
            </div>
        </div>
        
        <script type="text/javascript">
            (function() {{
                // Load shared Papaya resources if not already loaded
                if (typeof papaya === 'undefined') {{
                    var link = document.createElement('link');
                    link.rel = 'stylesheet';
                    link.type = 'text/css';
                    link.href = 'papaya.css';
                    document.head.appendChild(link);
                    
                    var script = document.createElement('script');
                    script.type = 'text/javascript';
                    script.src = 'papaya.js';
                    script.onload = function() {{
                        initViewer_{viewer_name}();
                    }};
                    document.head.appendChild(script);
                }} else {{
                    initViewer_{viewer_name}();
                }}
                
                function initViewer_{viewer_name}() {{
                    var params_{viewer_name} = [];
                    params_{viewer_name}["worldSpace"] = true;
                    params_{viewer_name}["expandable"] = true;
                    params_{viewer_name}["showControls"] = true;
                    params_{viewer_name}["kioskMode"] = false;
                    params_{viewer_name}["showImageButtons"] = true;
                    params_{viewer_name}["allowScroll"] = true;
                    params_{viewer_name}["smoothDisplay"] = true;
                    
                    // Start with empty viewer - user will manually load images
                    params_{viewer_name}["images"] = [];
                    
                    var container = document.getElementById('papaya_{viewer_name}');
                    if (container && typeof papaya !== 'undefined') {{
                        papaya.Container.addViewer(container, params_{viewer_name});
                    }}
                }}
                
                // Initialize when DOM is ready
                if (document.readyState === 'loading') {{
                    document.addEventListener('DOMContentLoaded', function() {{
                        setTimeout(function() {{
                            if (typeof papaya !== 'undefined') {{
                                initViewer_{viewer_name}();
                            }}
                        }}, 200);
                    }});
                }} else {{
                    setTimeout(function() {{
                        if (typeof papaya !== 'undefined') {{
                            initViewer_{viewer_name}();
                        }}
                    }}, 200);
                }}
            }})();
        </script>
        """
        
        return html_content
        
    except Exception as e:
        print(f"ERROR: Failed to create Papaya viewer: {str(e)}")
        return _generate_papaya_error_message(viewer_name, str(e))

def _generate_available_files_list(field_files, labels):
    """Generate HTML list items for available field files."""
    items = []
    for i, field_file in enumerate(field_files):
        label = labels[i] if i < len(labels) else f"Field {i+1}"
        filename = os.path.basename(field_file)
        items.append(f"<li>🧠 <strong>{label}:</strong> {filename}</li>")
    return "\n".join(items)

def _generate_papaya_error_message(viewer_name, error):
    """Generate error message HTML."""
    return f"""
    <div style="margin: 15px 0; padding: 15px; background-color: #f8d7da; border-radius: 8px; border: 1px solid #f5c6cb;">
        <h6 style="color: #721c24; margin-bottom: 10px;">❌ Papaya Viewer Error</h6>
        <p style="color: #721c24; margin: 0; font-size: 14px;">
            <strong>Viewer:</strong> {viewer_name}<br>
            <strong>Error:</strong> {error}
        </p>
    </div>
    """

def _generate_papaya_installation_guide(sample_file):
    """Generate HTML with Papaya installation instructions."""
    filename = os.path.basename(sample_file) if sample_file else "NIfTI files"
    
    return f"""
    <div class="papaya-fallback" style="margin: 15px 0;">
        <div style="background-color: #f8f9fa; border: 2px dashed #6c757d; border-radius: 8px; padding: 20px; text-align: center;">
            <div style="font-size: 18px; margin-bottom: 10px;">🧠</div>
            <h6 style="color: #495057; margin-bottom: 10px;">Papaya Viewer</h6>
            <p style="color: #6c757d; margin-bottom: 15px;">
                <strong>Files ready:</strong> {filename}
            </p>
            
            <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 12px; border-radius: 6px; margin-bottom: 15px;">
                <p style="color: #856404; margin: 0; font-size: 14px;">
                    <strong>⚠️ Papaya not found</strong><br>
                    Please install Papaya to enable interactive visualization.
                </p>
            </div>
            
            <div style="background-color: #e8f5e8; padding: 12px; border-radius: 6px; margin-bottom: 15px;">
                <p style="color: #2e7d32; margin: 0; font-size: 14px;">
                    💡 <strong>To install Papaya:</strong><br>
                    1. <code style="background: #333; color: #0f0; padding: 2px 4px;">git clone https://github.com/rii-mango/Papaya.git</code><br>
                    2. Place in project root directory<br>
                    3. Regenerate your report for interactive features!
                </p>
            </div>
            
            <div style="margin-top: 15px;">
                <button onclick="window.open('https://github.com/rii-mango/Papaya', '_blank')" 
                        style="background-color: #2196f3; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-right: 10px; font-size: 12px;">
                    🌐 Get Papaya
                </button>
            </div>
        </div>
    </div>
    """

# Legacy function for backward compatibility
def add_papaya_viewer(html_path, t1_file, overlay_file):
    """
    Legacy function - adds Papaya viewer to an existing HTML file.
    For new code, use create_papaya_viewer() instead.
    """
    report_dir = os.path.dirname(os.path.abspath(html_path))
    viewer_name = f"viewer_{abs(hash(f'{t1_file}_{overlay_file}')) % 10000}"
    
    viewer_html = create_papaya_viewer(
        report_dir=report_dir,
        viewer_name=viewer_name,
        t1_file=t1_file,
        field_files=[overlay_file],
        labels=["TI Field"]
    )
    
    try:
        # Read the HTML file
        with open(html_path, 'r') as f:
            html_content = f.read()
        
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