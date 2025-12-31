#!/usr/bin/env simnibs_python
"""
Electrode Placement Module for TI-Toolbox 3D Exporter

This module provides functionality for placing electrode objects on a scalp mesh
using Blender. It supports both:
- Direct .msh file input (extracts scalp automatically)
- Pre-existing scalp.stl files

The module is designed to work with simnibs_python (headless bpy).

Classes:
    ElectrodePlacementConfig: Configuration for electrode placement
    ElectrodePlacer: Main class for electrode placement operations
"""

import os
import logging
import struct
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass, field

from .utils import clear_blender_scene


@dataclass
class ElectrodePlacementConfig:
    """Configuration parameters for electrode placement.

    Attributes:
        subject_id: Subject identifier
        electrode_csv_path: Path to CSV file with electrode positions (Label,X,Y,Z)
        electrode_blend_path: Path to Blender file containing electrode template
        output_dir: Directory for output files (.blend, .glb, scalp.stl)
        
        # Scalp source (provide ONE of these):
        subject_msh_path: Path to SimNIBS .msh file (extracts scalp from tag 1005)
        scalp_stl_path: Path to existing scalp.stl file
        
        # Placement settings:
        scale_factor: Scaling factor for CSV coordinates (default: 1.0)
        electrode_diameter_mm: Electrode diameter in mm (default: 10.0)
        electrode_height_mm: Electrode height in mm (default: 6.0)
        electrode_size: (Deprecated) uniform scale for electrode objects (legacy)
        offset_distance: Distance to lift electrodes off scalp surface (default: 3.25 mm)
        text_offset: Offset for label text above electrode (default: 0.090)
        
        # Template object names:
        electrode_name: Name of electrode object in template (default: "Electrode")
        label_name: Name of label text object in template (default: "Label")
        
        # Advanced:
        skin_tag: SimNIBS tag for skin/scalp (default: 1005)
    """
    subject_id: str
    electrode_csv_path: str
    electrode_blend_path: str
    output_dir: str
    
    # Scalp source (one of these)
    subject_msh_path: Optional[str] = None
    scalp_stl_path: Optional[str] = None
    
    # Placement settings
    scale_factor: float = 1.0
    electrode_diameter_mm: float = 10.0
    electrode_height_mm: float = 6.0
    electrode_size: Optional[float] = None
    offset_distance: float = 3.25
    text_offset: float = 0.090
    
    # Template names
    electrode_name: str = "Electrode"
    label_name: str = "Label"
    
    # Advanced
    skin_tag: int = 1005

    # Optional montage highlighting: list of electrode pairs
    montage_pairs: Optional[List[Tuple[str, str]]] = None

    # Exports
    export_glb: bool = True

    # Visibility control:
    # - True: place the entire net
    # - False: place only electrodes referenced by montage_pairs (if provided)
    show_full_net: bool = True

    def validate(self) -> None:
        """Validate configuration paths and parameters."""
        # Check scalp source
        if not self.subject_msh_path and not self.scalp_stl_path:
            raise ValueError("Must provide either subject_msh_path or scalp_stl_path")
        
        if self.subject_msh_path and not os.path.exists(self.subject_msh_path):
            raise FileNotFoundError(f"Subject MSH not found: {self.subject_msh_path}")
        
        if self.scalp_stl_path and not os.path.exists(self.scalp_stl_path):
            raise FileNotFoundError(f"Scalp STL not found: {self.scalp_stl_path}")

        if not os.path.exists(self.electrode_csv_path):
            raise FileNotFoundError(f"Electrode CSV not found: {self.electrode_csv_path}")

        if not os.path.exists(self.electrode_blend_path):
            raise FileNotFoundError(f"Electrode template not found: {self.electrode_blend_path}")

        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)

        # Validate numeric parameters
        if self.scale_factor <= 0:
            raise ValueError(f"scale_factor must be > 0, got {self.scale_factor}")
        if self.electrode_diameter_mm <= 0:
            raise ValueError(f"electrode_diameter_mm must be > 0, got {self.electrode_diameter_mm}")
        if self.electrode_height_mm <= 0:
            raise ValueError(f"electrode_height_mm must be > 0, got {self.electrode_height_mm}")
        if self.electrode_size is not None and self.electrode_size <= 0:
            raise ValueError(f"electrode_size must be > 0, got {self.electrode_size}")
        if self.offset_distance < 0:
            raise ValueError(f"offset_distance must be >= 0, got {self.offset_distance}")
    
    @property
    def output_blend_path(self) -> str:
        """Path for output .blend file."""
        csv_name = os.path.splitext(os.path.basename(self.electrode_csv_path))[0]
        return os.path.join(self.output_dir, f"{self.subject_id}_electrodes_{csv_name}.blend")
    
    @property
    def output_glb_path(self) -> str:
        """Path for output .glb file."""
        csv_name = os.path.splitext(os.path.basename(self.electrode_csv_path))[0]
        return os.path.join(self.output_dir, f"{self.subject_id}_electrodes_{csv_name}.glb")
    
    @property
    def output_scalp_stl_path(self) -> str:
        """Path for output scalp.stl file."""
        return os.path.join(self.output_dir, "scalp.stl")


class ElectrodePlacer:
    """Place electrodes on scalp mesh using Blender.

    This class handles the complete electrode placement workflow:
    1. Extract scalp from MSH or load existing STL
    2. Create scalp mesh in Blender
    3. Load electrode templates
    4. Place electrodes with proper orientation
    5. Export results

    Works with simnibs_python (headless bpy).
    """

    def __init__(self, config: ElectrodePlacementConfig, logger: Optional[logging.Logger] = None):
        """Initialize ElectrodePlacer."""
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        
        # Validate configuration
        self.config.validate()
        
        import bpy 
        self.bpy = bpy

        from mathutils import Vector, Quaternion
        self.Vector = Vector
        self.Quaternion = Quaternion
        self._mm_to_blender_units: Optional[float] = None

    def _infer_mm_to_blender_units(self, scalp_obj) -> float:
        """Infer conversion factor from mm -> Blender units based on scalp size.

        SimNIBS meshes are typically in mm. Blender defaults to meters.
        We keep this simple and infer from the scalp bounding box:
        - If the scalp max dimension is > 10, we assume units are already mm (1mm == 1BU)
        - Otherwise we assume meters (1mm == 0.001BU)
        """
        try:
            max_dim = float(max(getattr(scalp_obj, "dimensions", (0.0, 0.0, 0.0))))
        except Exception:
            max_dim = 0.0

        # Head size is ~180mm (~0.18m). This threshold cleanly separates mm vs meters scenes.
        return 1.0 if max_dim > 10.0 else 0.001

    def _apply_electrode_dimensions(self, electrode_obj, template_obj) -> None:
        """Scale electrode_obj so it matches the desired diameter/height (in mm) in the scene."""
        desired_diam = float(self.config.electrode_diameter_mm)
        desired_h = float(self.config.electrode_height_mm)

        mm_to_bu = self._mm_to_blender_units or 1.0
        desired_diam_bu = desired_diam * mm_to_bu
        desired_h_bu = desired_h * mm_to_bu

        # Measure template dimensions in its local axes (assumes Z is height, X/Y is diameter).
        base_dims = getattr(template_obj, "dimensions", None)
        if not base_dims:
            # Fallback to legacy uniform scale if we can't measure the template.
            if self.config.electrode_size is not None:
                electrode_obj.scale = (self.config.electrode_size,) * 3
            return

        base_diam = float(max(base_dims[0], base_dims[1]))
        base_h = float(base_dims[2])
        if base_diam <= 0 or base_h <= 0:
            if self.config.electrode_size is not None:
                electrode_obj.scale = (self.config.electrode_size,) * 3
            return

        sx = desired_diam_bu / base_diam
        sy = sx
        sz = desired_h_bu / base_h
        electrode_obj.scale = (sx, sy, sz)

    def _electrode_min_local_z_scaled(self, electrode_obj) -> float:
        """Return the minimum local Z of the electrode geometry after object scaling.

        This is used to keep the electrode from penetrating the scalp when height changes.
        Assumes the electrode's local +Z is its "up" axis (which we align to surface normal).
        """
        try:
            zs = [float(v.co[2]) for v in electrode_obj.data.vertices]
            if not zs:
                return 0.0
            min_z = min(zs)
            # Account for object scaling along Z.
            return float(min_z) * float(electrode_obj.scale[2])
        except Exception:
            # Fallback: unknown geometry/origin; don't force extra offset.
            return 0.0

    def _extract_scalp_from_msh(self) -> Tuple[List[tuple], List[tuple]]:
        """Extract skin surface from SimNIBS .msh file.
        
        Returns:
            Tuple of (vertices, faces) as lists of tuples
        """
        import numpy as np
        import simnibs
        
        msh_path = self.config.subject_msh_path
        skin_tag = self.config.skin_tag
        
        self.logger.info(f"Loading MSH: {msh_path}")
        mesh = simnibs.read_msh(msh_path)
        
        # Get triangular elements (type 2) with skin tag
        triangular = mesh.elm.elm_type == 2
        skin_mask = mesh.elm.tag1 == skin_tag
        skin_triangles_mask = triangular & skin_mask
        
        triangle_nodes = mesh.elm.node_number_list[skin_triangles_mask][:, :3]
        num_triangles = len(triangle_nodes)
        
        self.logger.info(f"Found {num_triangles} skin triangles (tag {skin_tag})")
        
        if num_triangles == 0:
            raise ValueError(f"No skin triangles found with tag {skin_tag}")
        
        # Create vertex mapping
        unique_nodes = np.unique(triangle_nodes.flatten())
        node_to_idx = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_nodes)}
        
        # Extract vertices (1-indexed to 0-indexed)
        vertices = mesh.nodes.node_coord[unique_nodes - 1]
        
        # Remap faces
        faces = np.array([[node_to_idx[n] for n in tri] for tri in triangle_nodes])
        
        self.logger.info(f"Extracted {len(vertices)} vertices, {len(faces)} faces")
        
        # Convert to list of tuples
        return [tuple(v) for v in vertices], [tuple(f) for f in faces]

    def _load_scalp_stl(self) -> Tuple[List[tuple], List[tuple]]:
        """Load vertices and faces from existing STL file.
        
        Returns:
            Tuple of (vertices, faces) as lists of tuples
        """
        import numpy as np
        
        stl_path = self.config.scalp_stl_path
        self.logger.info(f"Loading STL: {stl_path}")
        
        vertices = []
        faces = []
        vertex_map = {}
        
        with open(stl_path, 'rb') as f:
            # Read header
            f.read(80)
            # Read triangle count
            num_triangles = struct.unpack('<I', f.read(4))[0]
            
            for _ in range(num_triangles):
                # Skip normal (3 floats)
                f.read(12)
                
                face_indices = []
                for _ in range(3):
                    v = struct.unpack('<fff', f.read(12))
                    # Use tuple as key for deduplication
                    if v not in vertex_map:
                        vertex_map[v] = len(vertices)
                        vertices.append(v)
                    face_indices.append(vertex_map[v])
                
                faces.append(tuple(face_indices))
                
                # Skip attribute byte count
                f.read(2)
        
        self.logger.info(f"Loaded {len(vertices)} vertices, {len(faces)} faces")
        return vertices, faces

    def _write_stl(self, vertices: List[tuple], faces: List[tuple], path: str) -> None:
        """Write binary STL file."""
        self.logger.info(f"Writing STL: {path}")
        
        with open(path, 'wb') as f:
            header = b"TI-Toolbox Scalp Mesh".ljust(80, b'\x00')
            f.write(header)
            f.write(struct.pack('<I', len(faces)))
            
            for face in faces:
                v0, v1, v2 = vertices[face[0]], vertices[face[1]], vertices[face[2]]
                
                # Calculate normal
                edge1 = (v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2])
                edge2 = (v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2])
                normal = (
                    edge1[1]*edge2[2] - edge1[2]*edge2[1],
                    edge1[2]*edge2[0] - edge1[0]*edge2[2],
                    edge1[0]*edge2[1] - edge1[1]*edge2[0]
                )
                length = (normal[0]**2 + normal[1]**2 + normal[2]**2) ** 0.5
                if length > 1e-12:
                    normal = (normal[0]/length, normal[1]/length, normal[2]/length)
                else:
                    normal = (0.0, 0.0, 1.0)
                
                f.write(struct.pack('<fff', *normal))
                f.write(struct.pack('<fff', *v0))
                f.write(struct.pack('<fff', *v1))
                f.write(struct.pack('<fff', *v2))
                f.write(struct.pack('<H', 0))


    def _create_scalp_mesh(self, vertices: List[tuple], faces: List[tuple]):
        """Create scalp mesh directly in Blender."""
        bpy = self.bpy
        
        self.logger.info("Creating scalp mesh in Blender...")
        
        mesh_data = bpy.data.meshes.new("Scalp_Mesh")
        mesh_data.from_pydata(vertices, [], faces)
        mesh_data.update()
        
        scalp = bpy.data.objects.new("Scalp", mesh_data)
        bpy.context.collection.objects.link(scalp)
        bpy.context.view_layer.update()
        
        return scalp

    def _load_templates(self):
        """Load electrode and label templates from blend file."""
        bpy = self.bpy
        
        self.logger.info(f"Loading templates: {self.config.electrode_blend_path}")
        
        with bpy.data.libraries.load(self.config.electrode_blend_path, link=False) as (src, dst):
            dst.objects = [self.config.electrode_name, self.config.label_name]
        
        ele_template = bpy.data.objects.get(self.config.electrode_name)
        txt_template = bpy.data.objects.get(self.config.label_name)
        
        if not ele_template or not txt_template:
            raise RuntimeError(
                f"Could not load '{self.config.electrode_name}' or "
                f"'{self.config.label_name}' from {self.config.electrode_blend_path}"
            )
        
        # Keep templates unlinked so they don't leak into the saved .blend
        # (we'll copy from them and then remove them before export).
        return ele_template, txt_template

    def _read_electrodes(self):
        """Read electrode positions from CSV file using SimNIBS utilities."""
        from simnibs.utils.csv_reader import read_csv_positions

        self.logger.info(f"Reading electrodes: {self.config.electrode_csv_path}")

        # Use SimNIBS's CSV reader
        type_, coordinates, extra, name, extra_cols, header = read_csv_positions(
            self.config.electrode_csv_path
        )

        # Yield electrode data for types that are actual electrodes
        for t, coord, n in zip(type_, coordinates, name):
            if t in ['Electrode', 'ReferenceElectrode']:
                label = n if n else "Electrode"
                x, y, z = coord
                yield label, x, y, z

    def _calculate_orientation(self, surface_normal):
        """Calculate electrode rotation to align with surface normal."""
        Vector = self.Vector
        Quaternion = self.Quaternion
        
        local_up = Vector((0, 0, 1))
        local_north = Vector((0, 1, 0))
        world_up = Vector((0, 0, 1))
        
        pitch_q = local_up.rotation_difference(surface_normal)
        cur_north = pitch_q @ local_north
        up_proj = (world_up - surface_normal * world_up.dot(surface_normal)).normalized()
        
        angle = cur_north.angle(up_proj)
        sign = 1.0 if surface_normal.dot(cur_north.cross(up_proj)) >= 0 else -1.0
        twist_q = Quaternion(surface_normal, angle * sign)
        
        return twist_q @ pitch_q

    def _place_single_electrode(
        self,
        ele_template,
        txt_template,
        label,
        x,
        y,
        z,
        scalp,
        scalp_eval,
        w2l,
        l2w,
        electrodes_collection,
        color_map: Dict[str, tuple],
    ) -> bool:
        """Place a single electrode on the scalp surface."""
        bpy = self.bpy
        Vector = self.Vector
        
        world_pos = Vector((x, y, z)) * self.config.scale_factor
        local_pos = w2l @ world_pos
        
        hit, loc, norm, _ = scalp_eval.closest_point_on_mesh(local_pos)
        if not hit:
            self.logger.warning(f"Could not project '{label}' onto scalp")
            return False
        
        surface_loc = scalp.matrix_world @ loc
        surface_norm = (l2w @ norm).normalized()
        
        # Create electrode
        dup = ele_template.copy()
        dup.data = ele_template.data.copy()
        dup.name = label
        self._apply_electrode_dimensions(dup, ele_template)
        electrodes_collection.objects.link(dup)
        # Hide Blender "relationship lines" (the black parent-connection line in viewport).
        try:
            dup.show_relationship_lines = False
        except Exception:
            pass

        # Optional: color montage pair electrodes (both electrodes share the pair color)
        if label in color_map:
            try:
                # Import locally so this file still imports outside Blender
                from .scene_setup import copy_material_with_color

                # Only apply highlight to the specific electrode material "Material.011"
                # and keep all other material slots intact.
                target_idx = None
                for i, mat in enumerate(list(getattr(dup.data, "materials", []))):
                    if not mat:
                        continue
                    # Match exact or suffix ".011" (covers "Material.011")
                    if mat.name == "Material.011" or mat.name.endswith(".011"):
                        target_idx = i
                        break

                if target_idx is not None:
                    base_mat = dup.data.materials[target_idx]
                    colored = copy_material_with_color(
                        base_mat,
                        name=f"{base_mat.name}_highlight_{label}",
                        base_color=color_map[label],
                    )
                    dup.data.materials[target_idx] = colored
                else:
                    self.logger.warning(
                        f"Could not find Material.011 slot on {label}; skipping highlight for this electrode."
                    )
            except Exception as e:
                self.logger.warning(f"Failed to apply highlight color for {label}: {e}")
        
        dup.rotation_mode = 'QUATERNION'
        dup.rotation_quaternion = self._calculate_orientation(surface_norm)
        # Ensure electrode doesn't penetrate the scalp when electrode height increases.
        # We treat config.offset_distance as a minimum lift (in mm).
        mm_to_bu = self._mm_to_blender_units or 1.0
        base_offset = float(self.config.offset_distance) * mm_to_bu
        # If the electrode origin is centered, min_z will be ~(-height/2); if it's at the base, min_z ~ 0.
        min_z_scaled = self._electrode_min_local_z_scaled(dup)
        tiny_gap = 0.1 * mm_to_bu  # 0.1mm safety gap
        required_offset = max(0.0, -min_z_scaled) + tiny_gap
        final_offset = max(base_offset, required_offset)
        dup.location = surface_loc + surface_norm * final_offset
        
        # Create label
        txt = txt_template.copy()
        txt.data = txt_template.data.copy()
        txt.name = f"Label_{label}"
        txt.parent = dup
        txt.matrix_parent_inverse = dup.matrix_world.inverted()
        # Keep label geometry independent of the electrode's (potentially non-uniform) scale.
        # This preserves label size and its relative offset.
        try:
            txt.inherit_scale = 'NONE'
            txt.scale = (1.0, 1.0, 1.0)
        except Exception:
            pass
        # Hide Blender "relationship lines" (the black parent-connection line in viewport).
        try:
            txt.show_relationship_lines = False
        except Exception:
            pass
        txt.data.body = label
        txt.location = Vector((0, 0, self.config.text_offset))
        electrodes_collection.objects.link(txt)
        
        return True

    def _build_pair_color_map(self) -> Dict[str, tuple]:
        """Build electrode->RGBA map for montage pair highlighting."""
        pairs = self.config.montage_pairs or []
        if not pairs:
            return {}

        # Pair colors in order: red, blue, green, yellow
        palette = [
            (1.0, 0.0, 0.0, 1.0),  # red
            (0.0, 0.25, 1.0, 1.0),  # blue
            (0.0, 0.8, 0.0, 1.0),  # green
            (1.0, 0.9, 0.0, 1.0),  # yellow
        ]

        color_map: Dict[str, tuple] = {}
        for idx, pair in enumerate(pairs[: len(palette)]):
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            a, b = str(pair[0]), str(pair[1])
            color = palette[idx]
            color_map[a] = color
            color_map[b] = color
        return color_map

    def _export_results(self) -> Tuple[str, str]:
        """Export scene to .blend and .glb files."""
        bpy = self.bpy
        
        blend_path = self.config.output_blend_path
        glb_path = self.config.output_glb_path
        
        self.logger.info(f"Saving: {blend_path}")
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)
        
        if self.config.export_glb:
            self.logger.info(f"Exporting: {glb_path}")
            try:
                bpy.ops.export_scene.gltf(
                    filepath=glb_path,
                    export_format='GLB',
                    use_selection=False
                )
            except Exception as e:
                self.logger.warning(f"GLB export failed: {e}")
        else:
            self.logger.info("Skipping GLB export (export_glb=False)")
        
        return blend_path, glb_path

    def place_electrodes(self) -> Tuple[bool, str]:
        """Execute electrode placement workflow.

        Returns:
            Tuple of (success: bool, message: str)
        """
        bpy = self.bpy
        
        self.logger.info(f"Starting electrode placement for subject {self.config.subject_id}")
        
        try:
            # Get scalp geometry
            if self.config.subject_msh_path:
                vertices, faces = self._extract_scalp_from_msh()
                # Save STL for reference
                self._write_stl(vertices, faces, self.config.output_scalp_stl_path)
            else:
                vertices, faces = self._load_scalp_stl()
            
            # Clear scene and create scalp mesh
            clear_blender_scene()
            scalp = self._create_scalp_mesh(vertices, faces)
            self._mm_to_blender_units = self._infer_mm_to_blender_units(scalp)

            # Create a single collection for all electrodes + labels
            electrodes_collection = bpy.data.collections.get("Electrodes")
            if electrodes_collection is None:
                electrodes_collection = bpy.data.collections.new("Electrodes")
                bpy.context.scene.collection.children.link(electrodes_collection)
            
            # Get evaluated scalp for BVH queries
            depsgraph = bpy.context.evaluated_depsgraph_get()
            scalp_eval = scalp.evaluated_get(depsgraph)
            
            # Prepare transformation matrices
            w2l = scalp.matrix_world.inverted()
            l2w = scalp.matrix_world.to_3x3()
            
            # Load templates
            ele_template, txt_template = self._load_templates()

            # Prepare montage pair highlight colors (optional)
            color_map = self._build_pair_color_map()

            # If montage-only: build allowed electrode set (and skip the rest)
            keep_labels = None
            if not self.config.show_full_net:
                keep_labels = set(color_map.keys())
                if not keep_labels:
                    self.logger.warning("show_full_net=False but no montage_pairs provided; placing full net.")
                    keep_labels = None
            
            # Place electrodes
            placed = 0
            failed = 0
            
            for label, x, y, z in self._read_electrodes():
                if keep_labels is not None and label not in keep_labels:
                    continue
                if self._place_single_electrode(
                    ele_template, txt_template, label, x, y, z,
                    scalp, scalp_eval, w2l, l2w, electrodes_collection, color_map
                ):
                    placed += 1
                else:
                    failed += 1
            
            self.logger.info(f"Placed {placed} electrodes ({failed} failed)")
            
            # Remove template objects so they don't get saved into the output .blend
            try:
                if ele_template:
                    bpy.data.objects.remove(ele_template, do_unlink=True)
                if txt_template:
                    bpy.data.objects.remove(txt_template, do_unlink=True)
            except Exception:
                pass

            # Export results
            blend_path, glb_path = self._export_results()
            
            success_msg = (
                f"Successfully placed {placed} electrodes.\n"
                f"Blend: {blend_path}\n"
                f"GLB: {glb_path}"
            )
            self.logger.info(success_msg)
            return True, success_msg
            
        except Exception as e:
            error_msg = f"Electrode placement failed: {e}"
            self.logger.error(error_msg)
            return False, error_msg
