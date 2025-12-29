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
from typing import Optional, Tuple, List
from dataclasses import dataclass, field


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
        electrode_size: Uniform scale for electrode objects (default: 50.0)
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
    electrode_size: float = 50.0
    offset_distance: float = 3.25
    text_offset: float = 0.090
    
    # Template names
    electrode_name: str = "Electrode"
    label_name: str = "Label"
    
    # Advanced
    skin_tag: int = 1005

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
        if self.electrode_size <= 0:
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
        
        # Import bpy (works with simnibs_python or blender)
        try:
            import bpy
            self.bpy = bpy
        except ImportError:
            raise ImportError(
                "bpy module not found. Run with simnibs_python or blender."
            )
        
        # Import mathutils
        try:
            from mathutils import Vector, Quaternion
            self.Vector = Vector
            self.Quaternion = Quaternion
        except ImportError:
            raise ImportError("mathutils not found. Run with simnibs_python or blender.")

    def _extract_scalp_from_msh(self) -> Tuple[List[tuple], List[tuple]]:
        """Extract skin surface from SimNIBS .msh file.
        
        Returns:
            Tuple of (vertices, faces) as lists of tuples
        """
        import numpy as np
        try:
            import simnibs
        except ImportError:
            raise ImportError("SimNIBS required to extract scalp from .msh files")
        
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

    def _clear_scene(self) -> None:
        """Remove all objects from Blender scene."""
        bpy = self.bpy
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in list(bpy.data.meshes):
            bpy.data.meshes.remove(mesh)

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
        
        for obj in (ele_template, txt_template):
            if obj.name not in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.link(obj)
            obj.hide_set(True)
            obj.hide_render = True
        
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

    def _place_single_electrode(self, ele_template, txt_template, label, x, y, z,
                                 scalp, scalp_eval, w2l, l2w) -> bool:
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
        dup.scale = (self.config.electrode_size,) * 3
        bpy.context.scene.collection.objects.link(dup)
        
        dup.rotation_mode = 'QUATERNION'
        dup.rotation_quaternion = self._calculate_orientation(surface_norm)
        dup.location = surface_loc + surface_norm * self.config.offset_distance
        
        # Create label
        txt = txt_template.copy()
        txt.data = txt_template.data.copy()
        txt.name = f"Label_{label}"
        txt.parent = dup
        txt.matrix_parent_inverse = dup.matrix_world.inverted()
        txt.data.body = label
        txt.location = Vector((0, 0, self.config.text_offset))
        bpy.context.scene.collection.objects.link(txt)
        
        return True

    def _export_results(self) -> Tuple[str, str]:
        """Export scene to .blend and .glb files."""
        bpy = self.bpy
        
        blend_path = self.config.output_blend_path
        glb_path = self.config.output_glb_path
        
        self.logger.info(f"Saving: {blend_path}")
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)
        
        self.logger.info(f"Exporting: {glb_path}")
        try:
            bpy.ops.export_scene.gltf(
                filepath=glb_path,
                export_format='GLB',
                use_selection=False
            )
        except Exception as e:
            self.logger.warning(f"GLB export failed: {e}")
        
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
            self._clear_scene()
            scalp = self._create_scalp_mesh(vertices, faces)
            
            # Get evaluated scalp for BVH queries
            depsgraph = bpy.context.evaluated_depsgraph_get()
            scalp_eval = scalp.evaluated_get(depsgraph)
            
            # Prepare transformation matrices
            w2l = scalp.matrix_world.inverted()
            l2w = scalp.matrix_world.to_3x3()
            
            # Load templates
            ele_template, txt_template = self._load_templates()
            
            # Place electrodes
            placed = 0
            failed = 0
            
            for label, x, y, z in self._read_electrodes():
                if self._place_single_electrode(
                    ele_template, txt_template, label, x, y, z,
                    scalp, scalp_eval, w2l, l2w
                ):
                    placed += 1
                else:
                    failed += 1
            
            self.logger.info(f"Placed {placed} electrodes ({failed} failed)")
            
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
