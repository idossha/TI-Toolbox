import nibabel.freesurfer.io as fsio
import argparse

def read_annot_file(annot_path, vertex_id=None):
    # Load annotation data
    labels, ctab, names = fsio.read_annot(annot_path)

    print(f"\nLoaded .annot file: {annot_path}")
    print(f"Number of vertices: {len(labels)}")
    print(f"Number of regions: {len(names)}\n")

    # Print all region names and their colors
    print("Regions and RGBA colors:")
    for i, name in enumerate(names):
        color = ctab[i][:4]  # R, G, B, A
        print(f"  {i:2d}: {name.decode('utf-8')} | Color: {color}")

    # If a specific vertex is given, show its label
    if vertex_id is not None:
        if 0 <= vertex_id < len(labels):
            label_val = labels[vertex_id]
            try:
                index = list(ctab[:, -1]).index(label_val)
                region_name = names[index].decode('utf-8')
                print(f"\nVertex {vertex_id} belongs to region: {region_name}")
            except ValueError:
                print(f"\nVertex {vertex_id} has an unknown label value: {label_val}")
        else:
            print(f"\nVertex ID {vertex_id} is out of range (0 to {len(labels) - 1})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read a FreeSurfer .annot file.")
    parser.add_argument("annot_path", help="Path to the .annot file")
    parser.add_argument("--vertex", type=int, help="Vertex ID to look up (optional)")

    args = parser.parse_args()
    read_annot_file(args.annot_path, args.vertex)
