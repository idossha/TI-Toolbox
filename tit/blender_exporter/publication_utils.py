#!/usr/bin/env simnibs_python
"""
TI-Toolbox Publication Visual Utilities

Backend utilities for creating publication-ready 3D visualizations.
Provides functionality to export and compose scalp, electrodes, GM, and ROI
into Blender scenes with proper transparency and electrode highlighting.
"""

import os
import logging
import shutil
import tempfile
import subprocess
from typing import Optional, Dict, List, Tuple

import numpy as np
import simnibs

from tit.core import get_path_manager, constants as const
from tit.blender_exporter.utils import (
    write_binary_stl,
    create_roi_mesh,
    extract_roi_region_no_zeros,
    parse_electrode_csv,
    find_mesh_files,
    find_electrode_csv,
    get_simulation_electrodes,
    create_electrode_geometry,
    export_mesh_to_ply,
    load_simulation_config,
    get_montage_from_config,
    get_eeg_net_from_config,
    write_ply_with_colors,
    field_to_colormap,
)

# Setup logger
logger = logging.getLogger(__name__)


class PublicationVisualizer:
    """Main class for creating publication-ready 3D visualizations."""

    def __init__(self, subject_id: str, simulation_name: str):
        """Initialize the visualizer.

        Args:
            subject_id: Subject ID (e.g., '001', '101')
            simulation_name: Name of the simulation
        """
        self.subject_id = subject_id
        self.simulation_name = simulation_name
        self.pm = get_path_manager()

        # Setup paths using PathManager
        self.subject_dir = self.pm.get_subject_dir(subject_id)
        self.sim_dir = self.pm.get_simulation_dir(subject_id, simulation_name)
        self.m2m_dir = self.pm.get_m2m_dir(subject_id)

        if not all([self.subject_dir, self.sim_dir, self.m2m_dir]):
            raise ValueError(f"Required directories not found for subject {subject_id}")

        # Load simulation configuration (auto-populates parameters)
        logger.info(f"Loading simulation configuration...")
        self.sim_config = load_simulation_config(subject_id, simulation_name)
        if self.sim_config:
            logger.info(f"  Simulation mode: {self.sim_config.get('simulation_mode')}")
            logger.info(f"  EEG net: {self.sim_config.get('eeg_net')}")
            logger.info(f"  Conductivity: {self.sim_config.get('conductivity_type')}")
            self.eeg_net = self.sim_config.get('eeg_net')
            self.electrode_pairs = self.sim_config.get('electrode_pairs', [])
            self.is_xyz_montage = self.sim_config.get('is_xyz_montage', False)
        else:
            logger.warning("No simulation config found, will try fallback methods")
            self.sim_config = {}
            self.eeg_net = None
            self.electrode_pairs = []
            self.is_xyz_montage = False

        # Create output directory using PathManager structure
        project_dir = self.pm.project_dir
        self.output_dir = os.path.join(
            project_dir,
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            "publication_visuals",
            f"{const.PREFIX_SUBJECT}{subject_id}",
            simulation_name
        )
        os.makedirs(self.output_dir, exist_ok=True)

        # Temporary directory for intermediate files
        self.temp_dir = tempfile.mkdtemp(prefix=f"pub_vis_{subject_id}_")
        logger.info(f"Initialized PublicationVisualizer for {subject_id}/{simulation_name}")
        logger.info(f"Output directory: {self.output_dir}")

    def __del__(self):
        """Cleanup temporary directory."""
        try:
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.debug(f"Cleaned up temporary directory: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temporary directory: {e}")

    def _get_field_name(self, mesh, requested_field: str) -> str:
        """Auto-detect correct field name from mesh.

        Tries common variations and provides helpful error if not found.

        Args:
            mesh: SimNIBS mesh object
            requested_field: User-requested field name

        Returns:
            Actual field name in the mesh

        Raises:
            KeyError: If field not found with helpful message
        """
        # Try the requested field name first
        if hasattr(mesh, 'field') and requested_field in mesh.field:
            return requested_field

        # Try common variations for TI fields
        variations = [
            requested_field,
            "TI_max",       # Common variation with underscore
            "TImax",        # Without underscore
            "TI_Max",       # Capitalized
            "normE",        # Electric field magnitude
            "E_magn"        # Electric field magnitude (alternative)
        ]

        for variant in variations:
            if hasattr(mesh, 'field') and variant in mesh.field:
                logger.info(f"Field '{requested_field}' not found, using '{variant}' instead")
                return variant

        # Field not found - provide helpful error
        available_fields = list(mesh.field.keys()) if hasattr(mesh, 'field') else []
        error_msg = (
            f"\nField '{requested_field}' not found in mesh.\n"
            f"Available fields: {available_fields}\n"
            f"\nTo use a different field, specify with --field parameter:\n"
            f"  --field TI_max\n"
        )
        raise KeyError(error_msg)

    def create_scalp_stl(self) -> str:
        """Create STL file for the scalp surface.

        Returns:
            Path to created scalp.stl file
        """
        scalp_stl_path = os.path.join(self.output_dir, "scalp.stl")
        logger.info("Creating scalp STL...")

        # Find tetrahedral mesh for scalp extraction
        # Use PathManager's simulation directory (already has Simulations/ path)
        ti_mesh_dir = os.path.join(self.sim_dir, "TI", "mesh")

        # Look for tetrahedral mesh file
        tetrahedral_mesh = None
        if os.path.exists(ti_mesh_dir):
            for file in os.listdir(ti_mesh_dir):
                if file.endswith("_TI_final.msh") or file.endswith("_T1.msh"):
                    tetrahedral_mesh = os.path.join(ti_mesh_dir, file)
                    break

        # Fallback: look in high_Frequency/mesh directory
        if not tetrahedral_mesh:
            hf_mesh_dir = os.path.join(self.sim_dir, "high_Frequency", "mesh")
            if os.path.exists(hf_mesh_dir):
                for file in os.listdir(hf_mesh_dir):
                    if file.endswith(".msh"):
                        tetrahedral_mesh = os.path.join(hf_mesh_dir, file)
                        break

        if not tetrahedral_mesh:
            raise FileNotFoundError(f"Tetrahedral mesh not found in {self.sim_dir}")

        # Extract scalp directly from tetrahedral mesh
        mesh = simnibs.read_msh(tetrahedral_mesh)

        # Get triangular elements (type 2) with skin tag (1005)
        triangular = mesh.elm.elm_type == 2
        skin_mask = mesh.elm.tag1 == 1005
        skin_triangles_mask = triangular & skin_mask

        triangle_nodes = mesh.elm.node_number_list[skin_triangles_mask][:, :3]
        num_triangles = len(triangle_nodes)

        if num_triangles == 0:
            raise ValueError("No skin triangles found with tag 1005")

        # Create vertex mapping
        unique_nodes = np.unique(triangle_nodes.flatten())
        node_to_idx = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_nodes)}

        # Extract vertices (1-indexed to 0-indexed)
        vertices = mesh.nodes.node_coord[unique_nodes - 1]

        # Remap faces
        faces = np.array([[node_to_idx[n] for n in tri] for tri in triangle_nodes])

        # Write STL file
        write_binary_stl(vertices, faces, scalp_stl_path, "TI-Toolbox Scalp Mesh")

        return scalp_stl_path

    def create_electrode_stl(self) -> Tuple[str, str]:
        """Create STL files for the electrode net (used and unused electrodes).

        Uses auto-populated config from simulation config.json when available.

        Returns:
            Tuple of (used_electrodes.stl, unused_electrodes.stl) paths
        """
        used_electrode_stl_path = os.path.join(self.output_dir, "electrodes_used.stl")
        unused_electrode_stl_path = os.path.join(self.output_dir, "electrodes_unused.stl")

        logger.info("Creating electrode visualization...")

        # Get electrode net from config if available
        eeg_net_csv = None
        if self.eeg_net:
            logger.info(f"  Using EEG net from config: {self.eeg_net}")
            # Construct path to EEG cap file
            eeg_positions_dir = os.path.join(self.m2m_dir, const.DIR_EEG_POSITIONS)
            eeg_net_csv = os.path.join(eeg_positions_dir, self.eeg_net)
            if not os.path.exists(eeg_net_csv):
                logger.warning(f"  EEG net file not found: {eeg_net_csv}, trying fallback")
                eeg_net_csv = None

        # Fallback to old method if config not available
        if not eeg_net_csv:
            logger.info("  Using fallback electrode search")
            # Look for electrode CSV in m2m_dir/eeg_positions
            eeg_positions_dir = os.path.join(self.m2m_dir, const.DIR_EEG_POSITIONS)
            if os.path.exists(eeg_positions_dir):
                csv_files = [f for f in os.listdir(eeg_positions_dir) if f.endswith('.csv')]
                if csv_files:
                    eeg_net_csv = os.path.join(eeg_positions_dir, csv_files[0])
                    logger.info(f"  Found EEG net: {csv_files[0]}")

        if not eeg_net_csv:
            raise FileNotFoundError(f"EEG net CSV not found in {self.m2m_dir}")

        # Parse CSV to get electrode positions
        electrodes = parse_electrode_csv(eeg_net_csv)
        logger.info(f"  Found {len(electrodes)} total electrodes")

        # Get electrodes used in simulation
        if self.electrode_pairs and not self.is_xyz_montage:
            # Use electrode pairs from config
            used_electrodes = set()
            for pair in self.electrode_pairs:
                if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    # Add both electrodes in the pair
                    used_electrodes.add(str(pair[0]))
                    used_electrodes.add(str(pair[1]))
            logger.info(f"  Using electrode pairs from config: {self.electrode_pairs}")
            logger.info(f"  Used electrodes: {used_electrodes}")
        else:
            # No config available - cannot determine used electrodes
            # For XYZ montages or old simulations without config, treat all as unused
            logger.warning("  No electrode pairs in config - cannot highlight used electrodes")
            logger.warning("  All electrodes will be treated as unused")
            used_electrodes = set()

        # Separate electrodes
        used_electrode_data = []
        unused_electrode_data = []

        for electrode in electrodes:
            name, x, y, z = electrode
            if name in used_electrodes:
                used_electrode_data.append(electrode)
            else:
                unused_electrode_data.append(electrode)

        # Create STL for used electrodes
        if used_electrode_data:
            all_vertices = []
            all_faces = []
            vertex_offset = 0

            for electrode in used_electrode_data:
                name, x, y, z = electrode
                # Increase electrode size significantly for visibility (radius=8mm, height=12mm)
                verts, faces = create_electrode_geometry(x, y, z, radius=8.0, height=12.0, segments=12)
                offset_faces = [[f[0] + vertex_offset, f[1] + vertex_offset, f[2] + vertex_offset] for f in faces]
                all_vertices.extend(verts)
                all_faces.extend(offset_faces)
                vertex_offset += len(verts)

            write_binary_stl(np.array(all_vertices), np.array(all_faces), used_electrode_stl_path, "TI-Toolbox Electrodes")
            logger.info(f"  Created {len(used_electrode_data)} used electrodes with increased size for visibility")

        # Create STL for unused electrodes
        if unused_electrode_data:
            all_vertices = []
            all_faces = []
            vertex_offset = 0

            for electrode in unused_electrode_data:
                name, x, y, z = electrode
                # Increase electrode size significantly for visibility (radius=8mm, height=12mm)
                verts, faces = create_electrode_geometry(x, y, z, radius=8.0, height=12.0, segments=12)
                offset_faces = [[f[0] + vertex_offset, f[1] + vertex_offset, f[2] + vertex_offset] for f in faces]
                all_vertices.extend(verts)
                all_faces.extend(offset_faces)
                vertex_offset += len(verts)

            write_binary_stl(np.array(all_vertices), np.array(all_faces), unused_electrode_stl_path, "TI-Toolbox Electrodes")
            logger.info(f"  Created {len(unused_electrode_data)} unused electrodes with increased size for visibility")

        return used_electrode_stl_path, unused_electrode_stl_path

    def create_blender_composition(self, scalp_stl: str, gm_ply: str, roi_ply: str) -> str:
        """Create the final Blender composition with electrode placement.

        Args:
            scalp_stl: Path to scalp STL
            gm_ply: Path to GM PLY
            roi_ply: Path to ROI PLY

        Returns:
            Path to final .blend file
        """
        final_blend_path = os.path.join(self.output_dir, f"{self.subject_id}_{self.simulation_name}_publication.blend")

        # Step 1: Use ElectrodePlacer to create electrode placement
        electrode_blend_path = None
        if self.eeg_net:
            logger.info("Placing electrodes using ElectrodePlacer class...")

            from tit.blender_exporter.electrode_placement import (
                ElectrodePlacer,
                ElectrodePlacementConfig,
            )

            # Setup paths for electrode placement
            eeg_positions_dir = os.path.join(self.m2m_dir, const.DIR_EEG_POSITIONS)
            electrode_csv_path = os.path.join(eeg_positions_dir, self.eeg_net)
            electrode_template_path = os.path.join(os.path.dirname(__file__), "Electrode.blend")
            subject_msh_path = os.path.join(self.m2m_dir, f"{self.subject_id}.msh")

            # Create configuration for electrode placement
            electrode_config = ElectrodePlacementConfig(
                subject_id=self.subject_id,
                electrode_csv_path=electrode_csv_path,
                electrode_blend_path=electrode_template_path,
                output_dir=self.output_dir,
                subject_msh_path=subject_msh_path,
                scalp_stl_path=scalp_stl,  # Use already created scalp STL
                scale_factor=1.0,
                electrode_size=60.0,  # Larger for visibility
                offset_distance=3.25,
                text_offset=0.090
            )

            # Create placer and execute
            try:
                placer = ElectrodePlacer(electrode_config, logger=logger)
                success, message = placer.place_electrodes()

                if success:
                    # Get the path to the generated .blend file
                    electrode_blend_path = electrode_config.output_blend_path
                    logger.info(f"Electrodes placed successfully: {electrode_blend_path}")
                else:
                    logger.warning(f"Electrode placement warning: {message}")
            except Exception as e:
                logger.warning(f"Could not place electrodes: {e}")

        # Get electrode pairs for material highlighting
        used_electrode_names = []
        if self.electrode_pairs and not self.is_xyz_montage:
            for pair in self.electrode_pairs:
                if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    used_electrode_names.append(str(pair[0]))
                    used_electrode_names.append(str(pair[1]))

        used_electrodes_str = ",".join(used_electrode_names)

        # Create a Blender script to compose everything
        blender_script = f"""
import bpy
import os
from mathutils import Vector, Euler

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Clear default collections
for collection in list(bpy.data.collections):
    bpy.data.collections.remove(collection)

# Import scalp STL
bpy.ops.import_mesh.stl(filepath=r"{scalp_stl}")
scalp = bpy.context.selected_objects[0]
scalp.name = "Scalp"
scalp.data.name = "Scalp_Mesh"

# Set scalp material with HASHED blend method (matches user's file)
scalp_material = bpy.data.materials.new(name="Material")
scalp_material.use_nodes = True
scalp_material.blend_method = 'HASHED'
bsdf = scalp_material.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.199, 0.180, 0.185, 1.0)  # Grayish
bsdf.inputs["Alpha"].default_value = 0.1
bsdf.inputs["Metallic"].default_value = 0.0
bsdf.inputs["Roughness"].default_value = 0.5
scalp.data.materials.append(scalp_material)

# Create "Electrodes" collection for grouping
electrodes_collection = bpy.data.collections.new("Electrodes")
bpy.context.scene.collection.children.link(electrodes_collection)

# Import electrodes from .blend file created by ElectrodePlacer
electrode_blend = r"{electrode_blend_path}" if "{electrode_blend_path}" != "None" else None
used_electrodes = "{used_electrodes_str}".split(",") if "{used_electrodes_str}" else []

if electrode_blend and os.path.exists(electrode_blend):
    try:
        # Link/append all objects from electrode blend file
        with bpy.data.libraries.load(electrode_blend, link=False) as (src, dst):
            dst.objects = src.objects

        # Add all imported objects to Electrodes collection
        for obj in dst.objects:
            if obj:
                # Skip scalp object from electrode file
                if "Scalp" in obj.name or "scalp" in obj.name.lower():
                    continue

                # Add to Electrodes collection (not main collection)
                electrodes_collection.objects.link(obj)

                # Keep all original materials from electrode template
                # DO NOT override them!

                # Make electrodes visible and renderable (like in user's file)
                obj.hide_set(False)
                obj.hide_render = False

    except Exception as e:
        print(f"Warning: Could not import electrodes from {{electrode_blend}}: {{e}}")
        import traceback
        traceback.print_exc()

# Import GM PLY
bpy.ops.import_mesh.ply(filepath=r"{gm_ply}")
gm = bpy.context.selected_objects[0]
gm.name = "gm"

# Set GM material with HASHED blend method (matches user's file)
gm_material = bpy.data.materials.new(name="Material.015")
gm_material.use_nodes = True
gm_material.blend_method = 'HASHED'

nodes = gm_material.node_tree.nodes
links = gm_material.node_tree.links

# Get the Principled BSDF
bsdf_gm = nodes.get("Principled BSDF")

# Create Color Attribute node to read vertex colors from PLY
color_attr_node = nodes.new(type='ShaderNodeVertexColor')
# PLY vertex colors are stored as 'Col' by default in Blender
if gm.data.vertex_colors:
    color_attr_node.layer_name = gm.data.vertex_colors[0].name
else:
    # Fallback: try to use 'Col' attribute name (common for PLY imports)
    color_attr_node.layer_name = 'Col'

# Connect vertex color to Base Color
links.new(color_attr_node.outputs['Color'], bsdf_gm.inputs['Base Color'])

# Set GM properties to match user's file
bsdf_gm.inputs["Alpha"].default_value = 0.3
bsdf_gm.inputs["Metallic"].default_value = 0.0
bsdf_gm.inputs["Roughness"].default_value = 0.5

gm.data.materials.append(gm_material)

# Single light (matches user's file - no 3-point lighting)
bpy.ops.object.light_add(type='POINT', location=(3.0290, 14.2176, 22.8508))
light = bpy.context.selected_objects[0]
light.name = "Light"
light.data.energy = 1000

# Set world background to transparent
bpy.context.scene.world.use_nodes = True
bg_node = bpy.context.scene.world.node_tree.nodes.get("Background")
if bg_node:
    bg_node.inputs["Color"].default_value = (0.05, 0.05, 0.05, 1.0)
    bg_node.inputs["Strength"].default_value = 1.0

# Set up perspective camera at user's exact location (not bird's eye, not orthographic)
bpy.ops.object.camera_add(location=(2.1216, 27.0958, 406.2056))
camera = bpy.context.selected_objects[0]
camera.name = "Camera"
camera.rotation_euler = (-0.0223, 0.0060, -0.0028)
bpy.context.scene.camera = camera

# Keep perspective camera (not orthographic)
camera.data.type = 'PERSP'
camera.data.lens = 50.0

# Set render settings for EEVEE (matches user's file)
bpy.context.scene.render.engine = 'BLENDER_EEVEE'
bpy.context.scene.render.film_transparent = True
bpy.context.scene.render.resolution_x = 2048
bpy.context.scene.render.resolution_y = 2048

# Save the blend file
bpy.ops.wm.save_as_mainfile(filepath=r"{final_blend_path}")
"""

        # Write and run the Blender script
        script_path = os.path.join(self.temp_dir, "compose_scene.py")
        with open(script_path, 'w') as f:
            f.write(blender_script)

        # Run Blender with the script
        cmd = [
            "blender",
            "--background",
            "--python", script_path
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Blender composition failed: {e}")
            print(f"STDOUT: {e.stdout.decode()}")
            print(f"STDERR: {e.stderr.decode()}")
            raise

        if os.path.exists(final_blend_path):
            return final_blend_path

        raise FileNotFoundError("Final blend file was not created")

    def run(self) -> str:
        """Run the complete publication visualization pipeline.

        Returns:
            Path to the final .blend file

        Raises:
            RuntimeError: If any step in the pipeline fails
        """
        logger.info("="*60)
        logger.info(f"Creating publication visualization")
        logger.info(f"  Subject: {self.subject_id}")
        logger.info(f"  Simulation: {self.simulation_name}")
        logger.info(f"  ROI: {self.roi}")
        logger.info(f"  Atlas: {self.atlas}")
        logger.info(f"  Field: {self.field_name}")
        logger.info("="*60)

        try:
            # Step 1: Create scalp STL
            logger.info("Step 1/4: Creating scalp STL...")
            scalp_stl = self.create_scalp_stl()
            logger.info(f"  Created: {scalp_stl}")

            # Step 2: Create GM PLY with field distribution
            logger.info("Step 2/4: Creating GM PLY with field distribution...")
            gm_ply = self.create_gm_ply()
            logger.info(f"  Created: {gm_ply}")

            # Step 3: Create ROI PLY with field distribution
            logger.info("Step 3/4: Creating ROI PLY with field distribution...")
            roi_ply = self.create_roi_ply()
            logger.info(f"  Created: {roi_ply}")

            # Step 4: Compose everything in Blender (including electrode placement)
            logger.info("Step 4/4: Composing final Blender scene with electrode placement...")
            final_blend = self.create_blender_composition(
                scalp_stl, gm_ply, roi_ply
            )
            logger.info(f"  Created: {final_blend}")

            logger.info("="*60)
            logger.info("Publication visualization completed successfully!")
            logger.info(f"Output: {final_blend}")
            logger.info("="*60)

            return final_blend

        except Exception as e:
            logger.error(f"Error during visualization creation: {e}", exc_info=True)
            raise RuntimeError(f"Publication visualization failed: {e}") from e


def create_publication_visualization(subject_id: str, simulation_name: str, roi: str) -> str:
    """Convenience function to create publication visualization.

    Args:
        subject_id: Subject ID
        simulation_name: Simulation name
        roi: ROI name

    Returns:
        Path to the final .blend file
    """
    visualizer = PublicationVisualizer(subject_id, simulation_name, roi)
    return visualizer.run()
