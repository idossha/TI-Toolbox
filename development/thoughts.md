Missing pieces for MVP:


**macOS arm64 native**: 
runs both flex-search and charm.
currently both do not run inside docker container on macOS arm64.

**Linux AMD**:
able to run without AFFINTY flag. 
can run a simulator? YES.
can run a charm? CPU usage reached 400%. TBD... it reached very far but did not complete.
can run a flex? 


---

Behavior to fix:

1. make sure nothing can be overwritten without a warning.
2. make sure new-user popup is not displayed if user clicked it. even if container was closed. 
3. if expecting the user to create a freesurfer directory, we need to make it explicit and grey it out if not there.



---

1. mTI optimization:
    - create a new method for mTI? 
    - should it be under the flex-opt?

2. mesh rendering:

Python Packages (via pip):
PyQt5 (Your GUI.sh already handles this)
PyOpenGL
pyvista
pyvistaqt
You likely ran: pip install PyQt5 PyOpenGL pyvista pyvistaqt
System Packages (via apt-get on Debian/Ubuntu):
xvfb: Provides the X virtual framebuffer needed for headless rendering.
libgl1-mesa-glx: Provides GLX-based Mesa OpenGL runtime.
libgl1-mesa-dri: Provides DRI-based Mesa OpenGL runtime (hardware acceleration interface).
libosmesa6: Provides the OSMesa (Off-Screen Mesa) software rendering library.
You need to run (after fixing GPG keys if necessary): apt-get update && apt-get install -y xvfb libgl1-mesa-glx libgl1-mesa-dri libosmesa6


3. add nir's citation





