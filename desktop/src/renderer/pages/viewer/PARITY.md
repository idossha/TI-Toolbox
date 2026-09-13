# Viewer responsibilities

Current architecture: [Architecture §7.1](../../../../../docs/dev/ARCHITECTURE.md#71-native-tetravox-is-installed-for-the-host-user).

TI-Toolbox owns subject/space selection, the file composition and saved composition catalogue.
Open writes a host-addressed native scene and launches the managed TetraVox application.
Legacy saved scenes are converted into a separate native copy; originals remain unchanged.

TetraVox owns camera, colormap, opacity, layers, file dialogs and saving the edited native scene.
TI's Save composition records inputs; it cannot capture later changes made in TetraVox.
The browser can download scene files but cannot install or launch a native application.

The dedicated Simulator/Optimizer/Analyzer WebGL selection panes remain inside TI-Toolbox.
Subject-volume preview opens explicitly in the native viewer; there is no live cross-app bridge.
