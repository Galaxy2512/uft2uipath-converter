"""Emit C# Windows UiPath workflows and test projects from typed script analysis.

- emitter.py: ComponentEmitter, one UFT action -> one workflow; shared helpers
- handlers.py: the handler table, one @emits handler per mapped node type
- emitters/: the handlers that decide which activities each UFT construct
  becomes (ui, flow, testing, functions)
- browser_scopes.py / window_scopes.py: group UI actions under Attach Browser/Window
- studio_xaml.py: final rewrite into the C# XAML form Studio saves
- project_emitter.py: test cases per ALM test and the Studio project (used by convert)
- project.py / batch.py: project.json metadata and the older manifest-based commands
"""
