# TI-Toolbox example-data store

The data store behind **Add example data?** / **Help ▸ Example data** in the TI-Toolbox desktop,
`python -m tit.examples` and the example notebook, organised the way
[3D Slicer's SlicerDataStore](https://github.com/Slicer/SlicerDataStore) (and Tetravox's sample
store) is: every file is an asset of the single `example-data` release of `idossha/TI-Toolbox`,
**named by its own sha256**, so a URL is

    https://github.com/idossha/TI-Toolbox/releases/download/example-data/<sha256>

and `tit.examples` verifies what it downloaded against the name before anything lands in a
project. What each hash *is* — file name, sample, source, licence — is listed in
`tit/examples/catalog.json` and on the wiki's *Example data* page. New samples are added there;
`dev/example-data/stage.py` builds and verifies the assets from the upstream zip and `publish.sh`
uploads them (never clobbering: an asset's content is its name).

Nothing here is original work. Every asset is derived from the SimNIBS example dataset
(`simnibs/example-dataset` v4.1, `simnibs4_examples.zip`), **GPL-3.0** — provenance and the
licence check are in `tit/scene/guide/PROVENANCE.md`. Head models are re-packed as one
`m2m_<id>.tar.gz` per subject; raw T1/T2 NIfTIs are byte-identical to upstream.
