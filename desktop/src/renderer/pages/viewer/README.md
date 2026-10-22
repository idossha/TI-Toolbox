# Viewer responsibilities

Current architecture: [Architecture §7.1](../../../../../docs/dev/ARCHITECTURE.md#71-ti-toolboxs-own-tetravox-is-the-only-one-it-launches).

TI-Toolbox owns subject/space selection and the file composition (the tree on this page).
Open writes a host-addressed native scene into the project and launches the managed TetraVox application.
Legacy server-backed saved scenes are converted into a separate native copy; originals remain unchanged.

TetraVox owns camera, colormap, opacity, layers and file dialogs.
Save scene asks the running TetraVox, through the desktop bridge, to save its active scene (camera and
appearance changes included) into the project; Saved scenes lists, reopens and deletes those files.
The browser can download a prepared scene file but cannot install or launch a native application.

The dedicated Simulator/Optimizer/Analyzer WebGL selection panes remain inside TI-Toolbox.
Subject-volume preview opens explicitly in the native viewer; there is no live sync between the panes and TetraVox.
