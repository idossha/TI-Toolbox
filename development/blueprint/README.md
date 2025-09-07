

Image building:

docker build -f `file` -t `image_name` .

where: 
file is Dockerfile.simnibs / Dockerfile.freesurfer etc.
image_name is idossha/simnibs:vX.X.X / idossha/ti-toolbox:vX.X.X

use the flag `--no-cache` when want to make sure no previous builds are used. 

Then:
docker push `image_name`
