

Image building:

docker build -f `file` -t `image_name` .

where: 
file is Dockerfile.simnibs / Dockerfile.freesurfer etc.
image_name is idossha/simnbs:vX.X.X / idossha/ti-toolbox:vX.X.X


Then:
docker push `image_name`
