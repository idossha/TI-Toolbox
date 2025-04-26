#!/bin/bash

# Input and Output directories
input_dir=$1
output_dir=$2
base_dir="base-niftis"

# Create the output directory if it doesn't exist
mkdir -p "$output_dir"

# Function to check if any screenshots were generated
function check_screenshots {
    local dir=$1
    if [ -z "$(ls -A "$dir"/*_montage.png 2>/dev/null)" ]; then
        echo "Error: No screenshots were generated."
        exit 1
    fi
}

# Check if there are any NIfTI files in the input directory
if [ -z "$(ls -A "$input_dir"/*.nii 2>/dev/null)" ] && [ -z "$(ls -A "$input_dir"/*.nii.gz 2>/dev/null)" ]; then
    echo "No NIfTI files found in the directory."
    exit 1
fi

# Iterate through each NIfTI file in the input directory
for nifti_file in "$input_dir"/*.{nii,nii.gz}; do
    # Check if the file exists
    if [ ! -e "$nifti_file" ]; then
        continue
    fi

    # Extract the filename without the extension
    filename=$(basename "$nifti_file")
    filename_without_ext="${filename%.*}"
    extension="${filename##*.}"

    # Handle .nii.gz extension specifically
    if [ "$extension" == "gz" ]; then
        filename_without_ext="${filename%.*.*}"
    fi

    echo "Processing $nifti_file"

    # Define the output image files
    axial_img="${output_dir}/${filename_without_ext}_axial.png"
    coronal_img="${output_dir}/${filename_without_ext}_coronal.png"
    sagittal_img="${output_dir}/${filename_without_ext}_sagittal.png"
    montage_img="${output_dir}/${filename_without_ext}_montage.png"

    # Take axial screenshot using Freeview
    freeview --viewsize 800 800 \
             -v "$base_dir/MNI152_T1_1mm.nii.gz:colormap=grayscale" \
             -v "$base_dir/neuro-ego.nii.gz:colormap=lut:lut=$base_dir/NeuroEgo.txt:isosurface=1" \
             -v "$base_dir/combined_spheres.nii.gz:colormap=binary:binary_color=0,0,255:isosurface=0:isosurface_color=0,0,255" \
             -v "$nifti_file:colormap=heat:heatscale=95,99.9:percentile=1:isosurface=1:isosurface_color=red" \
             --viewport axial -ras -4.49 -43.38 30.80 -zoom 0.7 --screenshot "$axial_img" 1
    sleep 1  # Adding a delay to ensure the command completes

    # Take coronal screenshot using Freeview
    freeview --viewsize 800 800 \
             -v "$base_dir/MNI152_T1_1mm.nii.gz:colormap=grayscale" \
             -v "$base_dir/neuro-ego.nii.gz:colormap=lut:lut=$base_dir/NeuroEgo.txt:isosurface=1" \
             -v "$base_dir/combined_spheres.nii.gz:colormap=binary:binary_color=0,0,255:isosurface=0:isosurface_color=0,0,255" \
             -v "$nifti_file:colormap=heat:heatscale=95,99.9:percentile=1:isosurface=1:isosurface_color=red" \
             --viewport coronal -ras -4.49 -43.38 30.80 -zoom 0.7 --screenshot "$coronal_img" 1
    sleep 1  # Adding a delay to ensure the command completes

    # Take sagittal screenshot using Freeview
    freeview --viewsize 800 800 \
             -v "$base_dir/MNI152_T1_1mm.nii.gz:colormap=grayscale" \
             -v "$base_dir/neuro-ego.nii.gz:colormap=lut:lut=$base_dir/NeuroEgo.txt:isosurface=1" \
             -v "$base_dir/combined_spheres.nii.gz:colormap=binary:binary_color=0,0,255:isosurface=0:isosurface_color=0,0,255" \
             -v "$nifti_file:colormap=heat:heatscale=95,99.9:percentile=1:isosurface=1:isosurface_color=red" \
             --viewport sagittal -ras -4.49 -43.38 30.80 -zoom 0.7 --screenshot "$sagittal_img" 1
    sleep 1  # Adding a delay to ensure the command completes

    # Check if screenshots were successfully created
    if [ ! -e "$axial_img" ] || [ ! -e "$coronal_img" ] || [ ! -e "$sagittal_img" ]; then
        echo "Failed to create screenshots for $nifti_file"
        continue
    fi

    # Combine the screenshots into a single image using ImageMagick
    magick "$axial_img" "$coronal_img" "$sagittal_img" +append "$montage_img"
    
    # Clean up individual view images if needed
    rm "$axial_img" "$coronal_img" "$sagittal_img"
done

# Convert all montage images to a single PDF file
montage_images=("${output_dir}"/*_montage.png)

# Check if any screenshots were generated
check_screenshots "$output_dir"

magick "${montage_images[@]}" "${output_dir}/nifti_screenshots.pdf"

echo "Screenshots have been saved to ${output_dir}/nifti_screenshots.pdf"

