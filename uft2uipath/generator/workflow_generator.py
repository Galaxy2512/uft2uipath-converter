from pathlib import Path

from uft2uipath.ast import BusinessComponent


class WorkflowGenerator:
    def generate_component_workflow(
        self,
        component: BusinessComponent,
        output_dir: str | Path,
    ) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        file_path = output_path / f"{component.name}.xaml"

        xaml = f"""<?xml version="1.0" encoding="utf-8"?>
<Activity mc:Ignorable="sap sap2010"
 xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"
 xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="{component.name}">
  </Sequence>
</Activity>
"""
        file_path.write_text(xaml, encoding="utf-8")
        return file_path