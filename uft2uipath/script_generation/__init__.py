"""Emit C# Windows UiPath workflows and test projects from typed script analysis.

- emitter.py: ComponentEmitter, one UFT action -> one workflow; shared helpers
- emitters/: the handlers that decide which activities each UFT construct
  becomes (ui, flow, testing, functions), registered in mapping.operation_registry
- browser_scopes.py / window_scopes.py: group UI actions under Attach Browser/Window
- studio_xaml.py: final rewrite into the C# XAML form Studio saves
- project_emitter.py: test cases per ALM test and the Studio project (used by convert)
- project.py / batch.py: project.json metadata and the older manifest-based commands
"""
