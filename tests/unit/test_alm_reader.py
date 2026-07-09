from uft2uipath.ast import Project
from uft2uipath.parser.alm_reader import AlmReader


def test_reader_returns_project(tmp_path):

    reader = AlmReader()

    project = reader.read(tmp_path)

    assert isinstance(project, Project)
    assert project.name == tmp_path.name