"""``/api/notebooks/*`` — the ``.ipynb`` files a notebook session edits (v1).

Thin HTTP over :mod:`tit.server.notebooks`; every path rule, every name check
and the nbformat read/write live there. One directory,
``<project>/code/ti-toolbox/notebooks``, which is also where the pipeline
canvas's "Export notebook" can now land a notebook instead of only handing it
to a download.

Import cost is deliberately small (``dev/route_import_guard.py``): ``nbformat``
is imported inside :mod:`tit.server.notebooks`' own functions, never here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from tit.server import notebooks as nb
from tit.server.schemas import Notebook, NotebookDeleted, NotebookEntry, NotebookList

router = APIRouter()

# NotebookError.code -> HTTP status. A name the user typed is a 422, a
# notebook that is not there is a 404, and a document that fails nbformat
# validation is a 422 as well: in every case the client can act on it.
_STATUS = {"bad-name": 422, "not-found": 404, "invalid": 422, "bad-notebook": 422}


def _project_root(request: Request) -> str:
    root = request.app.state.settings.project_dir
    if not root:
        raise HTTPException(status_code=409, detail="This server is not bound to a project.")
    return str(root)


def _fail(error: nb.NotebookError) -> HTTPException:
    return HTTPException(status_code=_STATUS.get(error.code, 422), detail=error.message)


@router.get(
    "/api/notebooks",
    response_model=NotebookList,
    summary="List the project's notebooks, newest first",
)
def list_notebooks(request: Request) -> dict[str, Any]:
    root = _project_root(request)
    return {
        "dir": str(nb.notebooks_dir(root)),
        "notebooks": [entry.as_dict() for entry in nb.list_notebooks(root)],
    }


@router.post(
    "/api/notebooks",
    response_model=Notebook,
    responses={409: {"description": "a notebook of that name already exists"}},
    summary="Create a notebook, or store one that was uploaded",
)
def create_notebook(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create ``name``.

    With no ``content``, the new notebook is the starter: a markdown cell and
    a first code cell that already imports ``tit`` and prints this project's
    root, so "the TI-Toolbox environment is automatically loaded" is something
    the author can see rather than be told.

    With ``content``, this is the import path — "Import .ipynb" in the UI, and
    the pipeline canvas saving its export. Same validation either way.
    """
    root = _project_root(request)
    name = body.get("name")
    if not isinstance(name, str):
        raise HTTPException(status_code=422, detail="'name' is required.")
    content = body.get("content")
    if content is not None and not isinstance(content, dict):
        raise HTTPException(status_code=422, detail="'content' must be a notebook object.")
    try:
        file_name = nb.normalise_name(name)
        path = nb.notebook_path(root, file_name)
        if path.exists() and not bool(body.get("overwrite", False)):
            raise HTTPException(
                status_code=409, detail=f"{file_name} already exists in this project."
            )
        document = content if content is not None else nb.new_notebook(root)
        nb.write_notebook(root, file_name, document)
        return {"name": file_name, "content": nb.read_notebook(root, file_name)}
    except nb.NotebookError as error:
        raise _fail(error) from error


@router.get("/api/notebooks/{name}", response_model=Notebook, summary="Read one notebook")
def read_notebook(request: Request, name: str) -> dict[str, Any]:
    root = _project_root(request)
    try:
        return {"name": nb.normalise_name(name), "content": nb.read_notebook(root, name)}
    except nb.NotebookError as error:
        raise _fail(error) from error


@router.put("/api/notebooks/{name}", response_model=NotebookEntry, summary="Write one notebook")
def write_notebook(request: Request, name: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    root = _project_root(request)
    content = body.get("content")
    if not isinstance(content, dict):
        raise HTTPException(status_code=422, detail="'content' must be a notebook object.")
    try:
        path = nb.write_notebook(root, name, content)
        info = path.stat()
        return {"name": path.name, "size": info.st_size, "modified": info.st_mtime}
    except nb.NotebookError as error:
        raise _fail(error) from error


@router.delete(
    "/api/notebooks/{name}", response_model=NotebookDeleted, summary="Delete one notebook"
)
def delete_notebook(request: Request, name: str) -> dict[str, Any]:
    root = _project_root(request)
    try:
        nb.delete_notebook(root, name)
    except nb.NotebookError as error:
        raise _fail(error) from error
    return {"deleted": nb.normalise_name(name)}
