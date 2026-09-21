# Unit tests for AlmReader (uft2uipath/parser/alm_reader.py): covers reading an
# ALM source folder and confirming it produces a Project AST object whose name
# defaults to the source folder's name.
from uft2uipath.ast import Project
from uft2uipath.parser.alm_reader import AlmReader


def test_reader_returns_project(tmp_path):

    reader = AlmReader()

    project = reader.read(tmp_path)

    assert isinstance(project, Project)
    assert project.name == tmp_path.name