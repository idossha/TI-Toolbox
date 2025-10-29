

Image building:

docker build -f `file` -t `image_name` .

where: 
file is Dockerfile.simnibs / Dockerfile.freesurfer etc.
`image_name` is idossha/simnibs:vX.X.X / idossha/freesurfer:vX.X.X

use the flag `--no-cache` when want to make sure no previous builds are used. 

Then:
docker push `image_name`

---

If you an ARM processor, you will need to using the following flag: --platform linux/amd64.

example:
```bash 
docker build --no-cache --platform linux/amd64 \
  -f Dockerfile.simnibs \
  -t idossha/simnibs:vX.X.X .
  ```

---

Always build the images when you are within the `blueprint` directory.