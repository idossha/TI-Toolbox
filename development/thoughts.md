


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