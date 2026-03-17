#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Electrode Placement Extension for TI-Toolbox

A minimal extension for placing electrode markers on head surfaces.
Supports:
- Fast loading of skin surfaces from m2m directory
- 3D manipulation (rotation, zoom, translation)
- Double-click to place markers
- Load EEG cap positions
- Export electrode coordinates with polarity naming (E1+, E1-, etc.)
"""

# Extension metadata (required)
EXTENSION_NAME = "Electrode Placement"
EXTENSION_DESCRIPTION = "Free placement of electrodes on head surfaces"

# Extension configuration
ALLOW_TAB_INTEGRATION = (
    False  # This extension can only be launched in a separate window
)

import logging
import sys
import os
import json
import csv
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QRadioButton,
    QFileDialog,
    QMessageBox,
    QComboBox,
    QInputDialog,
)

from OpenGL import GL, GLU, GLUT
import OpenGL

# Optional fallback to legacy QGLWidget
USE_QGL_FALLBACK = os.environ.get("TI_GUI_QGL_FALLBACK", "0") == "1"
try:
    from PyQt5.QtOpenGL import QGLWidget

    QGL_AVAILABLE = True
except Exception:
    QGLWidget = None
    QGL_AVAILABLE = False

# Decide which OpenGL widget base to use
OpenGLWidgetBase = QtWidgets.QOpenGLWidget
if USE_QGL_FALLBACK and QGL_AVAILABLE:
    OpenGLWidgetBase = QGLWidget

# Set conservative OpenGL format
try:
    fmt = QtGui.QSurfaceFormat()
    fmt.setVersion(2, 1)
    fmt.setProfile(QtGui.QSurfaceFormat.NoProfile)
    fmt.setRenderableType(QtGui.QSurfaceFormat.OpenGL)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)
except Exception:
    pass

from tit.paths import get_path_manager

PATH_MANAGER_AVAILABLE = True

# SimNIBS imports
from simnibs.mesh_tools import mesh_io


class _SkinSurface:
    """Lightweight replacement for the removed simnibs.mesh_tools.surface.Surface.

    Extracts a triangular skin surface from a SimNIBS mesh and provides the
    vertex/normal/triangle data needed by the OpenGL renderer plus a basic
    ray-triangle intersection method.
    """

    def __init__(self, mesh, tags):
        # Build triangle mask
        tri_mask = mesh.elm.elm_type == 2
        tag_mask = np.isin(mesh.elm.tag1, tags)
        skin_mask = tri_mask & tag_mask

        triangle_nodes = mesh.elm.node_number_list[skin_mask][:, :3]
        if len(triangle_nodes) == 0:
            raise ValueError(f"No skin triangles found for tags {tags}")

        unique_node_ids = np.unique(triangle_nodes.flatten())
        id_to_idx = {old: new for new, old in enumerate(unique_node_ids)}

        # Vertex positions (SimNIBS nodes are 1-indexed)
        self.nodes = mesh.nodes.node_coord[unique_node_ids - 1].astype(np.float64)

        # Remapped triangles (indices into self.nodes)
        self.tr_nodes = np.vectorize(id_to_idx.get)(triangle_nodes).astype(np.int32)

        # Per-vertex normals (area-weighted)
        self.nodes_normals = self._compute_normals()

    # ------------------------------------------------------------------
    def _compute_normals(self):
        normals = np.zeros_like(self.nodes)
        v0 = self.nodes[self.tr_nodes[:, 0]]
        v1 = self.nodes[self.tr_nodes[:, 1]]
        v2 = self.nodes[self.tr_nodes[:, 2]]
        face_normals = np.cross(v1 - v0, v2 - v0)
        for i in range(3):
            np.add.at(normals, self.tr_nodes[:, i], face_normals)
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        lengths[lengths == 0] = 1.0
        return (normals / lengths).astype(np.float64)

    # ------------------------------------------------------------------
    def interceptRay(self, ray_origin, ray_far):
        """Möller-Trumbore ray-triangle intersection.

        Returns (point, normal) of the closest hit, or (None, None).
        """
        ray_origin = np.asarray(ray_origin, dtype=np.float64)
        ray_dir = np.asarray(ray_far, dtype=np.float64) - ray_origin
        ray_dir /= np.linalg.norm(ray_dir)

        v0 = self.nodes[self.tr_nodes[:, 0]]
        v1 = self.nodes[self.tr_nodes[:, 1]]
        v2 = self.nodes[self.tr_nodes[:, 2]]

        e1 = v1 - v0
        e2 = v2 - v0
        h = np.cross(ray_dir, e2)
        a = np.einsum("ij,ij->i", e1, h)

        valid = np.abs(a) > 1e-10
        f = np.zeros_like(a)
        f[valid] = 1.0 / a[valid]

        s = ray_origin - v0
        u = f * np.einsum("ij,ij->i", s, h)
        valid &= (u >= 0.0) & (u <= 1.0)

        q = np.cross(s, e1)
        v = f * np.einsum("ij,ij->i", q, np.broadcast_to(ray_dir, q.shape))
        valid &= (v >= 0.0) & (u + v <= 1.0)

        t = f * np.einsum("ij,ij->i", e2, q)
        valid &= t > 1e-10

        if not np.any(valid):
            return None, None

        t_vals = t[valid]
        closest = np.argmin(t_vals)
        hit_idx = np.where(valid)[0][closest]

        point = ray_origin + t[hit_idx] * ray_dir
        # Interpolate normal from vertices
        tri = self.tr_nodes[hit_idx]
        normal = self.nodes_normals[tri].mean(axis=0)
        normal /= np.linalg.norm(normal)
        return point, normal


class GLSurfaceWidget(OpenGLWidgetBase):
    """OpenGL widget for rendering head surfaces and markers"""

    markerPlaced = QtCore.pyqtSignal(list)  # Signal when a marker is placed

    def __init__(self, parent=None):
        super(GLSurfaceWidget, self).__init__(parent)

        # Surfaces
        self.skin_surf = None

        # Display lists
        self.skin_model = 0
        self.eeg_markers_list = 0

        # Colors
        self.skin_color = [0.53, 0.8, 0.93]  # Light blue
        self.eeg_color = [0.0, 1.0, 0.0]  # Green - EEG positions

        # Electrode pair colors (8 pairs with distinct colors)
        self.electrode_pair_colors = [
            [1.0, 0.0, 0.0],  # E1: Red
            [0.5, 0.0, 0.5],  # E2: Purple
            [0.0, 0.0, 1.0],  # E3: Blue
            [1.0, 0.5, 0.0],  # E4: Orange
            [0.0, 0.8, 0.8],  # E5: Cyan
            [1.0, 0.0, 1.0],  # E6: Magenta
            [0.5, 0.5, 0.0],  # E7: Olive
            [1.0, 0.75, 0.8],  # E8: Pink
        ]

        # Camera/view parameters
        self.xRot = 90 * 16
        self.yRot = 0
        self.zRot = 0
        self.xTran = 0.0
        self.yTran = -20.0
        self.zTran = -400
        self.zoom = 1.0

        # Mouse interaction
        self.lastPos = QtCore.QPoint()

        # Matrices for unprojection
        self.model_matrix = None
        self.projection_matrix = None
        self.view = [0, 0, 800, 600]

        # Markers
        self.marker_positions = []
        self.eeg_positions = []
        self.eeg_names = []
        self.show_eeg_markers = False

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

    def loadMesh(self, mesh_fn):
        """Load mesh file and extract skin surface"""
        try:
            logger.debug(f"Loading mesh: {mesh_fn}")
            mesh_struct = mesh_io.read_msh(mesh_fn)

            # Extract skin surface
            logger.debug("Extracting skin surface...")
            self.skin_surf = _SkinSurface(mesh_struct, [5, 1005])

            # Create display list
            logger.debug("Creating OpenGL model...")
            self.skin_model = self.createSurfaceModel(self.skin_surf, self.skin_color)

            self.update()
            logger.debug("Mesh loaded successfully!")
            return True

        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to load mesh:\n{str(e)}")
            logger.debug(f"Error loading mesh: {e}")
            return False

    def loadEEGCap(self, csv_file):
        """
        Load EEG cap positions from CSV file using SimNIBS utilities.
        """
        try:
            from simnibs.utils.csv_reader import read_csv_positions

            self.eeg_positions = []
            self.eeg_names = []

            # Use SimNIBS's CSV reader
            type_, coordinates, extra, name, extra_cols, header = read_csv_positions(
                csv_file
            )

            # Extract positions and names for electrodes only
            for t, coord, n in zip(type_, coordinates, name):
                if t in ["Electrode", "ReferenceElectrode"] and n:
                    self.eeg_positions.append(coord.tolist())
                    self.eeg_names.append(n)

            if len(self.eeg_positions) > 0:
                self.show_eeg_markers = True
                self.update()
                return True, len(self.eeg_positions)
            else:
                logger.debug("No valid EEG positions found in file")
                return False, 0

        except Exception as e:
            logger.debug(f"Error loading EEG cap: {e}", exc_info=True)
            return False, 0

    def clearEEGCap(self):
        """Clear loaded EEG cap positions"""
        self.eeg_positions = []
        self.eeg_names = []
        self.show_eeg_markers = False
        self.update()

    def createSurfaceModel(self, surf, color):
        """Create OpenGL display list for a surface"""
        if surf is None or len(surf.nodes) == 0:
            return 0

        nodes_pos = np.array(surf.nodes, dtype="float32")
        node_normals = np.array(
            [normal for normal in surf.nodes_normals], dtype="float32"
        )
        nr_nodes = len(nodes_pos)
        node_colors = np.array([color] * nr_nodes, dtype="float32")

        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_NORMAL_ARRAY)
        GL.glEnableClientState(GL.GL_COLOR_ARRAY)

        GL.glVertexPointerf(nodes_pos)
        GL.glNormalPointerf(node_normals)
        GL.glColorPointerf(node_colors)

        genList = GL.glGenLists(1)
        GL.glNewList(genList, GL.GL_COMPILE)

        for vertices in surf.tr_nodes:
            GL.glDrawElements(GL.GL_TRIANGLES, 3, GL.GL_UNSIGNED_INT, vertices)

        GL.glEndList()

        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
        GL.glDisableClientState(GL.GL_NORMAL_ARRAY)
        GL.glDisableClientState(GL.GL_COLOR_ARRAY)

        return genList

    def initializeGL(self):
        """Initialize OpenGL context"""
        GL.glClearColor(1.0, 1.0, 1.0, 1.0)  # White background
        GL.glShadeModel(GL.GL_SMOOTH)

        # Lighting
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glEnable(GL.GL_NORMALIZE)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_DIFFUSE)

        light_ambient = [0.0, 0.0, 0.0, 1.0]
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, light_ambient)

    def paintGL(self):
        """Render the scene"""
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        # Set up projection
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        width = float(self.width())
        height = float(self.height())
        frustrumx = 60 * width / 700
        frustrumy = 60 * height / 700
        GL.glFrustum(-frustrumx, frustrumx, frustrumy, -frustrumy, 200, 500)

        # Set up modelview
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glTranslatef(self.xTran, self.yTran, self.zTran)
        GL.glRotatef(self.xRot / 16.0, 1.0, 0.0, 0.0)
        GL.glRotatef(self.yRot / 16.0, 0.0, 1.0, 0.0)
        GL.glRotatef(self.zRot / 16.0, 0.0, 0.0, 1.0)
        GL.glScalef(-self.zoom, self.zoom, self.zoom)

        # Draw surface
        if self.skin_model:
            GL.glCallList(self.skin_model)

        # Draw EEG markers if loaded
        if self.show_eeg_markers:
            self.drawEEGMarkers()

        # Draw electrode markers
        self.drawMarkers()

        # Store matrices for unprojection
        self.model_matrix = GL.glGetDoublev(GL.GL_MODELVIEW_MATRIX)
        self.projection_matrix = GL.glGetDoublev(GL.GL_PROJECTION_MATRIX)

    def resizeGL(self, width, height):
        """Handle window resize"""
        GL.glViewport(0, 0, width, height)
        self.view = [0, 0, width, height]

    def drawMarkers(self):
        """Draw all placed electrode markers as spheres with color coding"""
        if not self.marker_positions:
            return

        qobj = GLU.gluNewQuadric()

        for i, pos in enumerate(self.marker_positions):
            # Determine color based on electrode pair (E1+/- = pair 0, E2+/- = pair 1, etc.)
            pair_index = i // 2
            if pair_index < len(self.electrode_pair_colors):
                color = self.electrode_pair_colors[pair_index]
            else:
                # Fallback color if more than 8 pairs
                color = [0.5, 0.5, 0.5]  # Gray

            GL.glColor3f(*color)
            GL.glPushMatrix()
            GL.glTranslatef(pos[0], pos[1], pos[2])
            GLU.gluSphere(qobj, 5, 10, 10)
            GL.glPopMatrix()

    def drawEEGMarkers(self):
        """Draw EEG cap positions as small spheres"""
        if not self.eeg_positions:
            return

        qobj = GLU.gluNewQuadric()
        GL.glColor3f(*self.eeg_color)

        for pos in self.eeg_positions:
            GL.glPushMatrix()
            GL.glTranslatef(pos[0], pos[1], pos[2])
            GLU.gluSphere(qobj, 3, 8, 8)
            GL.glPopMatrix()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to place marker"""
        if self.skin_surf is None:
            return

        # Get click position
        x = float(event.pos().x())
        y = float(self.view[3] - event.pos().y())

        # Unproject to get ray
        Near = GLU.gluUnProject(
            x, y, 0.0, self.model_matrix, self.projection_matrix, self.view
        )
        Far = GLU.gluUnProject(
            x, y, 1.0, self.model_matrix, self.projection_matrix, self.view
        )

        # Find intersection with surface
        if self.skin_surf:
            point, normal = self.skin_surf.interceptRay(Near, Far)
            if point is not None:
                self.marker_positions.append(point)
                self.markerPlaced.emit(point.tolist())
                self.update()

    def mousePressEvent(self, event):
        """Store mouse position for drag operations"""
        self.lastPos = QtCore.QPoint(event.pos())

    def mouseMoveEvent(self, event):
        """Handle mouse drag for rotation/translation"""
        dx = event.x() - self.lastPos.x()
        dy = event.y() - self.lastPos.y()

        if event.buttons() & QtCore.Qt.LeftButton:
            # Rotation
            self.setXRotation(self.xRot - 8 * dy)
            self.setZRotation(self.zRot - 8 * dx)
        elif event.buttons() & QtCore.Qt.RightButton:
            # Translation
            self.setXTranslation(self.xTran + dx * 0.5)
            self.setYTranslation(self.yTran + dy * 0.5)

        self.lastPos = QtCore.QPoint(event.pos())

    def wheelEvent(self, event):
        """Handle mouse wheel for zoom"""
        delta = event.angleDelta().y()
        zoom = self.zoom + delta / 1200.0
        if 0.1 < zoom < 10:
            self.zoom = zoom
            self.update()

    def setXRotation(self, angle):
        angle = self.normalizeAngle(angle)
        if angle != self.xRot:
            self.xRot = angle
            self.update()

    def setYRotation(self, angle):
        angle = self.normalizeAngle(angle)
        if angle != self.yRot:
            self.yRot = angle
            self.update()

    def setZRotation(self, angle):
        angle = self.normalizeAngle(angle)
        if angle != self.zRot:
            self.zRot = angle
            self.update()

    def setXTranslation(self, distance):
        if distance != 0.0:
            self.xTran = distance
            self.update()

    def setYTranslation(self, distance):
        if distance != 0.0:
            self.yTran = distance
            self.update()

    def normalizeAngle(self, angle):
        """Keep angle in reasonable range"""
        while angle < 0:
            angle += 360 * 16
        while angle > 360 * 16:
            angle -= 360 * 16
        return angle

    def clearMarkers(self):
        """Remove all electrode markers"""
        self.marker_positions = []
        self.update()

    def updateMarkerPosition(self, index, position):
        """Update a specific marker's position"""
        if 0 <= index < len(self.marker_positions):
            self.marker_positions[index] = position
            self.update()


class ElectrodePlacementWidget(QtWidgets.QWidget):
    """Main widget for electrode placement"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path_manager = get_path_manager() if PATH_MANAGER_AVAILABLE else None
        self.current_subject = None
        self.current_m2m_dir = None
        self.initUI()

        # Populate subjects if path manager available
        if self.path_manager:
            self.populateSubjects()

    def initUI(self):
        """Initialize the user interface"""

        # Main layout
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)

        # Left panel (controls) - expanded by 30%
        left_panel = self.createLeftPanel()
        left_panel.setMaximumWidth(520)  # 400 * 1.3 = 520
        left_panel.setMinimumWidth(390)  # 300 * 1.3 = 390
        left_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding
        )

        # Right panel (OpenGL view)
        self.right_panel = self.createRightPanel()
        self.right_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Expanding
        )
        self.right_panel.setMaximumWidth(1000)  # Limit right panel width

        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.right_panel)

    def createLeftPanel(self):
        """Create the left control panel"""
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)

        # Subject selection section
        subject_group = QGroupBox("Select Subject")
        subject_layout = QVBoxLayout()

        self.subject_combo = QComboBox()
        self.subject_combo.currentTextChanged.connect(self.onSubjectChanged)
        subject_layout.addWidget(QLabel("Available Subjects:"))
        subject_layout.addWidget(self.subject_combo)

        # Load button
        self.load_btn = QPushButton("Load Subject")
        self.load_btn.clicked.connect(self.loadSurfaces)
        subject_layout.addWidget(self.load_btn)

        subject_group.setLayout(subject_layout)
        layout.addWidget(subject_group)

        # EEG Cap section
        eeg_group = QGroupBox("EEG Cap Positions")
        eeg_layout = QVBoxLayout()

        self.eeg_combo = QComboBox()
        eeg_layout.addWidget(QLabel("Available EEG Caps:"))
        eeg_layout.addWidget(self.eeg_combo)

        eeg_btn_layout = QHBoxLayout()

        self.load_eeg_btn = QPushButton("Load EEG Cap")
        self.load_eeg_btn.clicked.connect(self.loadEEGCap)
        eeg_btn_layout.addWidget(self.load_eeg_btn)

        self.clear_eeg_btn = QPushButton("Clear EEG")
        self.clear_eeg_btn.clicked.connect(self.clearEEGCap)
        eeg_btn_layout.addWidget(self.clear_eeg_btn)

        eeg_layout.addLayout(eeg_btn_layout)
        eeg_group.setLayout(eeg_layout)
        layout.addWidget(eeg_group)

        # Markers table
        table_group = QGroupBox("Electrode Markers")
        table_layout = QVBoxLayout()

        self.marker_table = QTableWidget()
        self.marker_table.setColumnCount(5)
        self.marker_table.setHorizontalHeaderLabels(["", "Name", "X", "Y", "Z"])

        # Configure header to resize columns proportionally
        header = self.marker_table.horizontalHeader()
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.Fixed
        )  # Checkbox column - fixed width
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )  # Name column - stretch
        header.setSectionResizeMode(
            2, QtWidgets.QHeaderView.Stretch
        )  # X column - stretch
        header.setSectionResizeMode(
            3, QtWidgets.QHeaderView.Stretch
        )  # Y column - stretch
        header.setSectionResizeMode(
            4, QtWidgets.QHeaderView.Stretch
        )  # Z column - stretch
        self.marker_table.setColumnWidth(0, 50)  # Checkbox column fixed width

        # Disable horizontal scrollbar since all columns should be visible
        self.marker_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        # Disable cell selection highlighting
        self.marker_table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.marker_table.setFocusPolicy(QtCore.Qt.StrongFocus)

        # Connect signal for coordinate changes
        self.marker_table.itemChanged.connect(self.onTableItemChanged)

        table_layout.addWidget(self.marker_table)

        # Table buttons
        table_btn_layout = QHBoxLayout()

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.clearMarkers)
        table_btn_layout.addWidget(clear_btn)

        delete_btn = QPushButton("Delete Checked")
        delete_btn.clicked.connect(self.deleteChecked)
        table_btn_layout.addWidget(delete_btn)

        table_layout.addLayout(table_btn_layout)

        # Export button
        export_btn = QPushButton("Export to JSON")
        export_btn.clicked.connect(self.exportToJSON)
        table_layout.addWidget(export_btn)

        table_group.setLayout(table_layout)
        layout.addWidget(table_group)

        layout.addStretch()

        return panel

    def createRightPanel(self):
        """Create the right panel with OpenGL widget"""
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)

        # Initialize GLUT
        try:
            GLUT.glutInit()
        except OpenGL.error.NullFunctionError:
            pass

        # OpenGL widget
        self.gl_widget = GLSurfaceWidget()
        self.gl_widget.markerPlaced.connect(self.onMarkerPlaced)
        self.gl_widget.setMinimumSize(
            600, 400
        )  # Set reasonable minimum size for OpenGL view
        layout.addWidget(self.gl_widget)

        # Status label
        self.status_label = QLabel("Select a subject to begin")
        layout.addWidget(self.status_label)

        return panel

    def populateSubjects(self):
        """Populate subjects dropdown using PathManager"""
        if not self.path_manager:
            return

        subjects = self.path_manager.list_simnibs_subjects()
        self.subject_combo.clear()

        if subjects:
            self.subject_combo.addItems(subjects)
            self.status_label.setText(f"Found {len(subjects)} subjects")
        else:
            self.status_label.setText(
                "No subjects found. Check your project directory."
            )

    def onSubjectChanged(self, subject_id):
        """Handle subject selection change"""
        if not subject_id or not self.path_manager:
            return

        self.current_subject = subject_id

        # Populate EEG caps for this subject
        eeg_caps = self.path_manager.list_eeg_caps(subject_id)
        self.eeg_combo.clear()

        if eeg_caps:
            self.eeg_combo.addItems(eeg_caps)
            self.status_label.setText(
                f"Subject {subject_id} selected. {len(eeg_caps)} EEG caps available."
            )
        else:
            self.status_label.setText(
                f"Subject {subject_id} selected. No EEG caps found."
            )

    def loadSurfaces(self):
        """Load surfaces for selected subject"""
        if not self.current_subject:
            QMessageBox.warning(self, "Warning", "Please select a subject")
            return

        if not self.path_manager:
            QMessageBox.warning(self, "Warning", "PathManager not available")
            return

        # Get m2m directory
        m2m_dir = self.path_manager.m2m(self.current_subject)
        if not m2m_dir or not os.path.isdir(m2m_dir):
            QMessageBox.critical(
                self,
                "Error",
                f"m2m directory not found for subject {self.current_subject}",
            )
            return

        self.current_m2m_dir = m2m_dir

        # Find mesh file
        mesh_file = Path(m2m_dir) / f"{self.current_subject}.msh"
        if not mesh_file.exists():
            # Try alternative naming
            msh_files = list(Path(m2m_dir).glob("*.msh"))
            if msh_files:
                mesh_file = msh_files[0]
            else:
                QMessageBox.critical(self, "Error", f"No mesh file found in {m2m_dir}")
                return

        # Load the mesh
        self.status_label.setText(f"Loading {mesh_file.name}...")
        QApplication.processEvents()

        if self.gl_widget.loadMesh(str(mesh_file)):
            self.status_label.setText(
                f"Loaded subject {self.current_subject} | "
                f"Double-click to place markers"
            )
        else:
            self.status_label.setText("Failed to load mesh")

    def loadEEGCap(self):
        """Load selected EEG cap"""
        if not self.current_subject or not self.path_manager:
            QMessageBox.warning(self, "Warning", "Please load a subject first")
            return

        cap_file = self.eeg_combo.currentText()
        if not cap_file:
            QMessageBox.warning(self, "Warning", "No EEG cap selected")
            return

        eeg_pos_dir = self.path_manager.eeg_positions(self.current_subject) or ""
        cap_path = os.path.join(eeg_pos_dir, cap_file)

        success, count = self.gl_widget.loadEEGCap(cap_path)
        if success:
            self.status_label.setText(f"Loaded {count} EEG positions from {cap_file}")
        else:
            QMessageBox.critical(self, "Error", f"Failed to load EEG cap: {cap_file}")

    def clearEEGCap(self):
        """Clear loaded EEG cap"""
        self.gl_widget.clearEEGCap()
        self.status_label.setText("EEG cap cleared")

    def onMarkerPlaced(self, position):
        """Handle new marker placement with automatic naming"""
        row = self.marker_table.rowCount()

        # Generate electrode name (E1+, E1-, E2+, E2-, ...)
        electrode_num = (row // 2) + 1
        polarity = "+" if row % 2 == 0 else "-"
        electrode_name = f"E{electrode_num}{polarity}"

        # Temporarily disconnect signal to avoid triggering on programmatic changes
        self.marker_table.itemChanged.disconnect(self.onTableItemChanged)

        self.marker_table.insertRow(row)

        # Add checkbox for deletion - use QTableWidgetItem with checkState for better visibility
        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
        checkbox_item.setCheckState(QtCore.Qt.Unchecked)
        self.marker_table.setItem(row, 0, checkbox_item)

        # Add marker data - name is non-editable, XYZ are editable on double-click
        name_item = QTableWidgetItem(electrode_name)
        name_item.setFlags(
            name_item.flags() & ~QtCore.Qt.ItemIsEditable
        )  # Non-editable
        self.marker_table.setItem(row, 1, name_item)

        # XYZ columns are editable (default behavior allows double-click to edit)
        x_item = QTableWidgetItem(f"{position[0]:.2f}")
        y_item = QTableWidgetItem(f"{position[1]:.2f}")
        z_item = QTableWidgetItem(f"{position[2]:.2f}")
        self.marker_table.setItem(row, 2, x_item)
        self.marker_table.setItem(row, 3, y_item)
        self.marker_table.setItem(row, 4, z_item)

        # Color-code the row based on electrode pair
        pair_index = row // 2
        if pair_index < len(self.gl_widget.electrode_pair_colors):
            color = self.gl_widget.electrode_pair_colors[pair_index]
            # Convert to QColor (0-255 range)
            bg_color = QtGui.QColor(
                int(color[0] * 255), int(color[1] * 255), int(color[2] * 255), 50
            )
            for col in range(1, 5):
                self.marker_table.item(row, col).setBackground(bg_color)

        # Reconnect signal
        self.marker_table.itemChanged.connect(self.onTableItemChanged)

        self.status_label.setText(
            f"Marker {electrode_name} placed at "
            f"({position[0]:.1f}, {position[1]:.1f}, {position[2]:.1f})"
        )

    def clearMarkers(self):
        """Clear all markers"""
        reply = QMessageBox.question(
            self,
            "Confirm",
            "Clear all markers?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.marker_table.setRowCount(0)
            self.gl_widget.clearMarkers()
            self.status_label.setText("All markers cleared")

    def onTableItemChanged(self, item):
        """Handle table item changes (XYZ coordinates)"""
        row = item.row()
        col = item.column()

        # Only handle XYZ columns (2, 3, 4)
        if col not in [2, 3, 4]:
            return

        try:
            # Get current XYZ values
            x = float(self.marker_table.item(row, 2).text())
            y = float(self.marker_table.item(row, 3).text())
            z = float(self.marker_table.item(row, 4).text())

            # Update marker position in GL widget
            new_position = np.array([x, y, z])
            self.gl_widget.updateMarkerPosition(row, new_position)

            electrode_name = self.marker_table.item(row, 1).text()
            self.status_label.setText(
                f"Updated {electrode_name} to ({x:.1f}, {y:.1f}, {z:.1f})"
            )
        except (ValueError, AttributeError) as e:
            # Invalid input, revert
            logger.debug(f"Invalid coordinate value: {e}")

    def deleteChecked(self):
        """Delete all checked markers"""
        rows_to_delete = []

        # Find all checked rows
        for row in range(self.marker_table.rowCount()):
            checkbox_item = self.marker_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == QtCore.Qt.Checked:
                rows_to_delete.append(row)

        if not rows_to_delete:
            QMessageBox.information(self, "Info", "No markers selected for deletion")
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm",
            f"Delete {len(rows_to_delete)} checked marker(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # Temporarily disconnect signal
            self.marker_table.itemChanged.disconnect(self.onTableItemChanged)

            # Delete in reverse order to maintain indices
            for row in reversed(rows_to_delete):
                self.marker_table.removeRow(row)
                if row < len(self.gl_widget.marker_positions):
                    self.gl_widget.marker_positions.pop(row)

            # Renumber and recolor remaining markers
            for i in range(self.marker_table.rowCount()):
                electrode_num = (i // 2) + 1
                polarity = "+" if i % 2 == 0 else "-"
                electrode_name = f"E{electrode_num}{polarity}"

                name_item = QTableWidgetItem(electrode_name)
                name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.marker_table.setItem(i, 1, name_item)

                # Recolor row
                pair_index = i // 2
                if pair_index < len(self.gl_widget.electrode_pair_colors):
                    color = self.gl_widget.electrode_pair_colors[pair_index]
                    bg_color = QtGui.QColor(
                        int(color[0] * 255),
                        int(color[1] * 255),
                        int(color[2] * 255),
                        50,
                    )
                    for col in range(1, 5):
                        if self.marker_table.item(i, col):
                            self.marker_table.item(i, col).setBackground(bg_color)

            # Reconnect signal
            self.marker_table.itemChanged.connect(self.onTableItemChanged)

            self.gl_widget.update()
            self.status_label.setText(f"Deleted {len(rows_to_delete)} marker(s)")

    def exportToJSON(self):
        """Export marker coordinates to JSON file in stim_configs directory"""
        if self.marker_table.rowCount() == 0:
            QMessageBox.warning(self, "Warning", "No markers to export")
            return

        if not self.current_m2m_dir:
            QMessageBox.warning(self, "Warning", "No subject loaded")
            return

        # Ask for configuration name
        config_name, ok = QInputDialog.getText(
            self,
            "Export Configuration",
            "Enter configuration name:",
            text="electrode_config",
        )

        if not ok or not config_name:
            return

        # Ask for stimulation type
        stim_type, ok = QInputDialog.getItem(
            self, "Stimulation Type", "Select stimulation type:", ["U", "M"], 0, False
        )

        if not ok:
            return

        # Create stim_configs directory if it doesn't exist
        stim_configs_dir = os.path.join(self.current_m2m_dir, "stim_configs")
        os.makedirs(stim_configs_dir, exist_ok=True)

        # Build electrode positions dictionary
        electrode_positions = {}

        for row in range(self.marker_table.rowCount()):
            name = self.marker_table.item(row, 1).text()
            x = float(self.marker_table.item(row, 2).text())
            y = float(self.marker_table.item(row, 3).text())
            z = float(self.marker_table.item(row, 4).text())

            electrode_positions[name] = [x, y, z]

        # Build configuration with new structure
        config = {
            "name": config_name,
            "type": stim_type,
            "electrode_positions": electrode_positions,
        }

        # Save to JSON file
        output_file = os.path.join(stim_configs_dir, f"{config_name}.json")

        try:
            with open(output_file, "w") as f:
                json.dump(config, f, indent=2)

            QMessageBox.information(
                self,
                "Success",
                f"Configuration saved to:\n{output_file}\n\n"
                f"Name: {config_name}\n"
                f"Type: {'Unipolar' if stim_type == 'U' else 'Multipolar'}\n"
                f"Electrodes: {len(electrode_positions)}",
            )
            self.status_label.setText(
                f"Exported {len(electrode_positions)} electrodes to {config_name}.json"
            )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")


class ElectrodePlacementWindow(QtWidgets.QDialog):
    """Dialog wrapper for floating window mode"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Electrode Placement")
        # Let window size adapt to panel content
        self.setWindowFlag(QtCore.Qt.Window)

        # Embed the widget
        self.widget = ElectrodePlacementWidget(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)

        # Connect close event to properly close the widget
        self.finished.connect(self.widget.close)


def main(parent=None):
    """
    Main entry point for the extension.
    This function is called when the extension is launched.
    """
    window = ElectrodePlacementWindow(parent)
    window.show()
    return window


# Alternative entry point (for flexibility)
def run(parent=None):
    """Alternative entry point."""
    main(parent)


if __name__ == "__main__":
    main()
