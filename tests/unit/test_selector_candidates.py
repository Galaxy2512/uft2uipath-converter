from uft2uipath.mapping.selector_candidates import MAX_CONFIDENCE, propose


def step(cls, name, properties, identification):
    return {"class": cls, "name": name, "properties": properties, "identification": identification}


def web_chain(target_class="WebEdit", properties=None, identification=None, page_title="Welcome: Mercury Tours"):
    page_properties = {"micclass": "Page"}
    if page_title:
        page_properties["title"] = page_title
    return [
        step("Browser", "B", {"micclass": "Browser"}, ["micclass"]),
        step("Page", "P", page_properties, ["micclass"]),
        step(target_class, "t",
             properties if properties is not None else
             {"micclass": target_class, "type": "text", "name": "userName", "html tag": "INPUT"},
             identification if identification is not None else ["micclass", "type", "name", "html tag"]),
    ]


def test_web_selector_uses_page_title_and_identification_properties():
    candidate = propose(web_chain())

    assert candidate.selector == (
        '<html title="Welcome: Mercury Tours" />'
        '<webctrl type="text" name="userName" tag="INPUT" />'
    )
    assert candidate.kind == "web"
    assert candidate.verified is False and candidate.requires_review is True
    assert "browser_app_unspecified" in candidate.issues
    assert any("name='userName'" in evidence.replace('"', "'") for evidence in candidate.evidence)


def test_stronger_identifiers_score_higher_and_stay_capped():
    weak = propose(web_chain(properties={"micclass": "WebEdit", "html tag": "INPUT"},
                             identification=["micclass", "html tag"]))
    strong = propose(web_chain(properties={"micclass": "WebEdit", "html tag": "INPUT",
                                           "html id": "user", "name": "userName"},
                               identification=["micclass", "html tag", "html id", "name"]))

    assert weak.confidence < strong.confidence <= MAX_CONFIDENCE
    assert 'id="user"' in strong.selector


def test_missing_page_title_lowers_confidence_and_is_reported():
    with_title = propose(web_chain())
    without = propose(web_chain(page_title=None))

    assert without.confidence < with_title.confidence
    assert "page_title_unknown" in without.issues
    assert without.selector.startswith("<html />")


def test_type_is_only_used_for_input_elements():
    candidate = propose(web_chain(target_class="WebList",
                                  properties={"micclass": "WebList", "type": "select-one",
                                              "name": "fromPort", "html tag": "SELECT"},
                                  identification=["micclass", "type", "name", "html tag"]))

    assert 'type=' not in candidate.selector
    assert '<webctrl name="fromPort" tag="SELECT" />' in candidate.selector


def test_descriptive_properties_are_mapped_like_repository_properties():
    chain = [step("Browser", None, {"version": "Mozilla .*"}, ["version"]),
             step("Page", None, {"title": "Welcome"}, ["title"]),
             step("WebEdit", None, {"name": "userName", "html tag": "INPUT"}, ["name", "html tag"])]

    candidate = propose(chain)

    assert candidate.selector == '<html title="Welcome" /><webctrl name="userName" tag="INPUT" />'


def test_desktop_selector_uses_window_class_title_and_control_id():
    chain = [step("Dialog", "Login Dialog", {"micclass": "Dialog", "title": "Login", "nativeclass": "#32770"},
                  ["micclass", "title", "nativeclass"]),
             step("WinEdit", "Agent Name:", {"micclass": "WinEdit", "nativeclass": "Edit",
                                             "attached text": "Agent Name:", "window id": 3001},
                  ["micclass", "nativeclass", "attached text"])]

    candidate = propose(chain)

    assert candidate.kind == "desktop"
    assert candidate.selector == (
        '<wnd title="Login" cls="#32770" />'
        '<wnd cls="Edit" aaname="Agent Name:" ctrlid="3001" />'
    )
    assert "process_name_unspecified" in candidate.issues


def test_unsupported_classes_get_no_selector():
    chain = [step("Window", "W", {"micclass": "Window"}, ["micclass"]),
             step("ActiveX", "Progress", {"micclass": "ActiveX"}, ["micclass"])]

    candidate = propose(chain)

    assert candidate.selector is None and candidate.confidence == 0.0
    assert candidate.issues == ["unsupported_class: ActiveX"]


def test_values_are_xml_escaped():
    candidate = propose(web_chain(properties={"micclass": "WebButton", "name": 'a"b&c',
                                              "html tag": "INPUT"},
                                  identification=["micclass", "name", "html tag"]))

    assert 'name="a&quot;b&amp;c"' in candidate.selector
