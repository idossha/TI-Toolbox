import bpy
import json
from mathutils import Vector

# -------------------------
# Helper functions
# -------------------------

def safe_name(datablock):
    return datablock.name if datablock else None


def vector_to_list(v):
    return [round(x, 6) for x in v]


def make_json_safe(value):
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    elif isinstance(value, (list, tuple)):
        return [make_json_safe(v) for v in value]
    elif isinstance(value, dict):
        return {k: make_json_safe(v) for k, v in value.items()}
    else:
        return str(value)


def extract_custom_properties(id_block):
    props = {}
    for key in id_block.keys():
        if key == "_RNA_UI":
            continue
        props[key] = make_json_safe(id_block[key])
    return props

# -------------------------
# File-level metadata
# -------------------------

data = {
    "file": {
        "path": bpy.data.filepath,
        "blender_version": bpy.app.version_string,
    },
    "scenes": [],
    "objects": [],
    "materials": [],
    "images": [],
    "collections": [],
    "libraries": [],
}


# -------------------------
# Scene data
# -------------------------

for scene in bpy.data.scenes:
    scene_data = {
        "name": scene.name,
        "frame_range": [scene.frame_start, scene.frame_end],
        "render_engine": scene.render.engine,
        "unit_system": scene.unit_settings.system,
        "custom_properties": extract_custom_properties(scene),
    }
    data["scenes"].append(scene_data)


# -------------------------
# Object data
# -------------------------

for obj in bpy.data.objects:
    obj_data = {
        "name": obj.name,
        "type": obj.type,
        "visible": obj.visible_get(),
        "location": vector_to_list(obj.location),
        "rotation": vector_to_list(obj.rotation_euler),
        "scale": vector_to_list(obj.scale),
        "collections": [c.name for c in obj.users_collection],
        "custom_properties": extract_custom_properties(obj),
        "materials": [],
        "mesh_stats": None,
    }

    # Materials
    for slot in obj.material_slots:
        obj_data["materials"].append(safe_name(slot.material))

    # Mesh statistics
    if obj.type == "MESH" and obj.data:
        mesh = obj.data
        obj_data["mesh_stats"] = {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "faces": len(mesh.polygons),
            "has_uvs": bool(mesh.uv_layers),
            "has_vertex_colors": bool(mesh.vertex_colors),
        }

    data["objects"].append(obj_data)


# -------------------------
# Materials
# -------------------------

for mat in bpy.data.materials:
    mat_data = {
        "name": mat.name,
        "users": mat.users,
        "use_nodes": mat.use_nodes,
        "custom_properties": extract_custom_properties(mat),
    }

    if mat.use_nodes and mat.node_tree:
        mat_data["nodes"] = [node.type for node in mat.node_tree.nodes]

    data["materials"].append(mat_data)


# -------------------------
# Images / textures
# -------------------------

for img in bpy.data.images:
    img_data = {
        "name": img.name,
        "filepath": img.filepath,
        "source": img.source,
        "size": list(img.size),
        "users": img.users,
    }
    data["images"].append(img_data)


# -------------------------
# Collections
# -------------------------

for col in bpy.data.collections:
    col_data = {
        "name": col.name,
        "object_count": len(col.objects),
        "children": [child.name for child in col.children],
        "custom_properties": extract_custom_properties(col),
    }
    data["collections"].append(col_data)


# -------------------------
# Linked libraries
# -------------------------

for lib in bpy.data.libraries:
    lib_data = {
        "filepath": lib.filepath,
        "users_id": lib.users_id,
    }
    data["libraries"].append(lib_data)


# -------------------------
# Output
# -------------------------

# Print readable summary
print("=== BLEND FILE METADATA SUMMARY ===")
print(json.dumps(data, indent=2))

# Optional: write to JSON file next to the blend file
if bpy.data.filepath:
    output_path = bpy.data.filepath.replace(".blend", "_metadata.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nMetadata written to: {output_path}")

