# Generates one UiPath XAML workflow file per UFT BusinessComponent by
# rendering each of its Steps via ActivityGenerator and wrapping the results
# in a Sequence activity.

from xml.sax.saxutils import quoteattr
from pathlib import Path

from uft2uipath.ast import BusinessComponent
from uft2uipath.generator.activity_generator import ActivityGenerator


class WorkflowGenerator:
    """Writes one legacy workflow per business component. Legacy path, not used by convert."""
    def __init__(self, activity_generator: ActivityGenerator | None = None):
        """Use the given activity generator, or a default one."""
        self.activity_generator = activity_generator or ActivityGenerator()

    def generate_component_workflow(
        self,
        component: BusinessComponent,
        output_dir: str | Path,
    ) -> Path:
        """Write the workflow of one component and return its path."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        file_path = output_path / f"{component.name}.xaml"

        activities = "\n".join(
            f"    {self.activity_generator.generate(step)}"
            for step in component.steps
        )

        xaml = f"""<?xml version="1.0" encoding="utf-8"?>
<Activity mc:Ignorable="sap sap2010"
 xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"
 xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
 xmlns:ui="http://schemas.uipath.com/workflow/activities"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName={quoteattr(str(component.name))}>
{activities}
  </Sequence>
</Activity>
"""
        file_path.write_text(xaml, encoding="utf-8")
        return file_path