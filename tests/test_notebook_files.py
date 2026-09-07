"""Notebook file IO and ``/api/notebooks/*``.

The claim under test is SUNA's (docs/ARCHITECTURE.md §16.3 there): the
``.ipynb`` on disk *is* the document. A notebook read and written back
unchanged must come out the same, or every notebook in a project becomes a
merge conflict the moment two tools disagree about it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("nbformat")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server import notebooks as nb  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    get_path_manager(str(tmp_path))
    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


# --------------------------------------------------------------------------
# names and paths
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "given,expected",
    [
        ("analysis", "analysis.ipynb"),
        ("analysis.ipynb", "analysis.ipynb"),
        ("  Analysis 2 ", "Analysis 2.ipynb"),
        ("a_b-c.1", "a_b-c.1.ipynb"),
    ],
)
def test_names_that_are_accepted(given: str, expected: str) -> None:
    assert nb.normalise_name(given) == expected


@pytest.mark.parametrize(
    "given", ["", "../escape", "a/b", ".hidden", "/abs", "x" * 200, "a\x00b", "..", "a\\b"]
)
def test_names_that_are_refused(given: str) -> None:
    # Refused, never sanitised: silently rewriting a name is how a save lands
    # somewhere the author never looked.
    with pytest.raises(nb.NotebookError) as error:
        nb.normalise_name(given)
    assert error.value.code == "bad-name"


def test_the_directory_is_the_pipeline_export_directory(tmp_path: Path) -> None:
    assert nb.notebooks_dir(tmp_path) == tmp_path / "code" / "ti-toolbox" / "notebooks"


# --------------------------------------------------------------------------
# reading and writing
# --------------------------------------------------------------------------


def test_a_new_notebook_loads_the_environment(tmp_path: Path) -> None:
    document = nb.new_notebook()
    assert document["nbformat"] == 4
    assert document["metadata"]["kernelspec"]["name"] == "simnibs"
    code = [c for c in document["cells"] if c["cell_type"] == "code"]
    assert len(code) == 1
    source = code[0]["source"]
    # The maintainer's ask, made visible rather than asserted in prose.
    assert "from tit import catalog, get_path_manager" in source
    assert "import simnibs" in source
    assert "from tit.sim import SimulationConfig" in source
    assert "from tit.analyzer import Analyzer" in source


def test_every_name_the_starter_cell_uses_exists() -> None:
    """The starter cell must RUN, not merely look right.

    Its first version called ``pm.project_root``, which does not exist, so the
    very first cell of the very first notebook raised an AttributeError. Each
    attribute it touches is checked against the real class here, off the source
    text, so the cell and the API cannot drift apart again.
    """
    import inspect

    from tit import catalog
    from tit.paths import PathManager

    source = nb.starter_source()
    for attribute in ("project_dir", "list_simulations"):
        assert f"pm.{attribute}" in source
        assert hasattr(PathManager, attribute), attribute
    assert "catalog.subject_ids(pm)" in source
    assert callable(catalog.subject_ids)
    # No name the cell reads off `pm` may be one PathManager lacks.
    used = set(re.findall(r"\bpm\.([A-Za-z_][A-Za-z0-9_]*)", source))
    assert used <= set(dir(PathManager)), used - set(dir(PathManager))
    # And it must be syntactically a program.
    compile(source, "<starter>", "exec")
    assert inspect.cleandoc(source)


def test_the_example_notebook_is_a_worked_example(tmp_path: Path) -> None:
    document = nb.example_notebook()
    kinds = [cell["cell_type"] for cell in document["cells"]]
    assert kinds == ["markdown", "code", "code", "code", "code"]

    prose = document["cells"][0]["source"]
    # The prose exercises every markdown feature the renderer claims: heading,
    # list, bold, italic, inline code, link, table, block and inline math.
    for token in ("# ", "## ", "1. ", "**", "*nothing to install*", "`tit`", "](http", "| --- |", "$$", "$2\\,"):
        assert token in prose, token

    code = [cell["source"] for cell in document["cells"] if cell["cell_type"] == "code"]
    assert "import simnibs" in code[0]
    assert "pd.DataFrame" in code[1]
    assert "calc.get_TI_vectors" in code[2]
    assert "matplotlib" in code[3]
    # Without the inline magic this kernel's formatter offers a Figure only as
    # text/plain, and the example's headline output is the words
    # "<Figure size 900x340>" rather than a picture.
    assert "%matplotlib inline" in code[3]
    for index, source in enumerate(code):
        # IPython magics are not Python, so the plot cell is checked without
        # its magic lines rather than skipped.
        program = "\n".join(line for line in source.splitlines() if not line.startswith("%"))
        compile(program, f"<example {index}>", "exec")


def test_the_example_is_seeded_once_and_stays_deleted(tmp_path: Path) -> None:
    assert nb.seed_example(tmp_path) is True
    assert [entry.name for entry in nb.list_notebooks(tmp_path)] == [nb.EXAMPLE_NAME]
    assert nb.list_notebooks(tmp_path)[0].example is True
    # Idempotent: a second listing must not rewrite the user's edits away.
    assert nb.seed_example(tmp_path) is False

    nb.delete_notebook(tmp_path, nb.EXAMPLE_NAME)
    # Deleting it is a decision, not an accident the next listing undoes.
    assert nb.seed_example(tmp_path) is False
    assert nb.list_notebooks(tmp_path) == []


def test_the_examples_directory_is_the_only_one_a_name_may_carry() -> None:
    assert nb.normalise_name("examples/getting-started.ipynb") == nb.EXAMPLE_NAME
    assert nb.normalise_name("examples/x") == "examples/x.ipynb"
    for bad in ["examples/../escape", "other/x", "examples/a/b", "examples/.hidden"]:
        with pytest.raises(nb.NotebookError):
            nb.normalise_name(bad)


def test_a_user_notebook_sorts_above_the_example(tmp_path: Path) -> None:
    # The example is reference material; the author's own work is what they came
    # for, so it is never pushed below a file the app wrote for them.
    nb.seed_example(tmp_path)
    nb.write_notebook(tmp_path, "mine", nb.new_notebook())
    assert [entry.name for entry in nb.list_notebooks(tmp_path)] == ["mine.ipynb", nb.EXAMPLE_NAME]


def test_write_read_round_trip_is_byte_identical(tmp_path: Path) -> None:
    document = nb.new_notebook()
    nb.write_notebook(tmp_path, "round", document)
    first = nb.notebook_path(tmp_path, "round").read_bytes()
    nb.write_notebook(tmp_path, "round", nb.read_notebook(tmp_path, "round"))
    assert nb.notebook_path(tmp_path, "round").read_bytes() == first


def test_outputs_survive_the_round_trip(tmp_path: Path) -> None:
    document = nb.new_notebook()
    document["cells"][1]["outputs"] = [
        {"output_type": "stream", "name": "stdout", "text": "2\n"},
        {
            "output_type": "execute_result",
            "data": {"text/plain": "4", "image/png": "iVBORw0KGgo="},
            "metadata": {},
            "execution_count": 1,
        },
    ]
    document["cells"][1]["execution_count"] = 1
    nb.write_notebook(tmp_path, "outs", document)
    back = nb.read_notebook(tmp_path, "outs")
    outputs = back["cells"][1]["outputs"]
    assert outputs[0]["text"] == "2\n"
    assert outputs[1]["data"]["image/png"] == "iVBORw0KGgo="


def test_an_invalid_notebook_is_refused_rather_than_written(tmp_path: Path) -> None:
    with pytest.raises(nb.NotebookError) as error:
        nb.write_notebook(tmp_path, "bad", {"cells": "not a list", "nbformat": 4})
    assert error.value.code == "invalid"
    assert not nb.notebook_path(tmp_path, "bad").exists()


def test_a_partial_write_leaves_no_temporary_behind(tmp_path: Path) -> None:
    nb.write_notebook(tmp_path, "clean", nb.new_notebook())
    directory = nb.notebooks_dir(tmp_path)
    assert [p.name for p in directory.iterdir()] == ["clean.ipynb"]


def test_listing_is_newest_first_and_empty_when_there_is_nothing(tmp_path: Path) -> None:
    assert nb.list_notebooks(tmp_path) == []
    nb.write_notebook(tmp_path, "old", nb.new_notebook())
    nb.write_notebook(tmp_path, "new", nb.new_notebook())
    import os

    os.utime(nb.notebook_path(tmp_path, "old"), (1_000_000, 1_000_000))
    assert [entry.name for entry in nb.list_notebooks(tmp_path)] == ["new.ipynb", "old.ipynb"]


def test_reading_something_that_is_not_a_notebook(tmp_path: Path) -> None:
    nb.ensure_notebooks_dir(tmp_path)
    nb.notebook_path(tmp_path, "junk").write_text("this is not JSON")
    with pytest.raises(nb.NotebookError) as error:
        nb.read_notebook(tmp_path, "junk")
    assert error.value.code == "bad-notebook"


# --------------------------------------------------------------------------
# the routes
# --------------------------------------------------------------------------


def test_notebook_routes_create_read_write_delete(client: TestClient, project: Path) -> None:
    listed = client.get("/api/notebooks", headers=BEARER)
    assert listed.status_code == 200
    assert listed.json()["dir"].endswith("code/ti-toolbox/notebooks")
    # The first listing a project ever gets seeds the worked example.
    assert [n["name"] for n in listed.json()["notebooks"]] == [nb.EXAMPLE_NAME]

    created = client.post("/api/notebooks", headers=BEARER, json={"name": "first"})
    assert created.status_code == 200
    assert created.json()["name"] == "first.ipynb"
    assert "get_path_manager" in json.dumps(created.json()["content"])

    again = client.post("/api/notebooks", headers=BEARER, json={"name": "first"})
    assert again.status_code == 409

    fetched = client.get("/api/notebooks/first.ipynb", headers=BEARER)
    assert fetched.status_code == 200
    document = fetched.json()["content"]

    document["cells"].append(
        {"cell_type": "markdown", "metadata": {}, "source": "# added", "id": "extra1"}
    )
    saved = client.put(
        "/api/notebooks/first.ipynb", headers=BEARER, json={"content": document}
    )
    assert saved.status_code == 200
    assert saved.json()["name"] == "first.ipynb"

    reloaded = client.get("/api/notebooks/first.ipynb", headers=BEARER).json()["content"]
    assert reloaded["cells"][-1]["source"] == "# added"

    assert len(client.get("/api/notebooks", headers=BEARER).json()["notebooks"]) == 2
    assert client.delete("/api/notebooks/first.ipynb", headers=BEARER).status_code == 200
    assert [n["name"] for n in client.get("/api/notebooks", headers=BEARER).json()["notebooks"]] == [
        nb.EXAMPLE_NAME
    ]


def test_notebook_import_stores_a_supplied_document(client: TestClient, project: Path) -> None:
    # "Import .ipynb", and the pipeline canvas saving its export, are the
    # same call: a name and a document.
    document = nb.new_notebook()
    document["metadata"]["ti_toolbox"] = {"pipeline": {"version": 1}}
    posted = client.post(
        "/api/notebooks", headers=BEARER, json={"name": "imported", "content": document}
    )
    assert posted.status_code == 200
    back = client.get("/api/notebooks/imported.ipynb", headers=BEARER).json()["content"]
    assert back["metadata"]["ti_toolbox"]["pipeline"]["version"] == 1


def test_notebook_routes_refuse_a_traversal(client: TestClient) -> None:
    # The router's own path matching stops a separator before this code sees
    # it; what must not happen is a 200 or a file outside the directory.
    for name in ["..%2Fescape", ".hidden"]:
        response = client.get(f"/api/notebooks/{name}", headers=BEARER)
        assert response.status_code in (404, 422), name


def test_notebook_routes_report_a_missing_file_as_404(client: TestClient) -> None:
    assert client.get("/api/notebooks/nope.ipynb", headers=BEARER).status_code == 404
    assert client.delete("/api/notebooks/nope.ipynb", headers=BEARER).status_code == 404


def test_notebook_routes_reject_a_bad_document(client: TestClient) -> None:
    response = client.put(
        "/api/notebooks/x.ipynb", headers=BEARER, json={"content": {"cells": "no"}}
    )
    assert response.status_code == 422


def test_notebook_routes_need_auth(client: TestClient) -> None:
    assert client.get("/api/notebooks").status_code == 401
