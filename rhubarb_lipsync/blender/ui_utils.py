import bpy
from bpy.types import Context, Window, Area, UILayout, SoundSequence, Sound
from typing import Any, Callable, Iterator, Type


def find_areas_by_type(context: Context, area_type: str) -> Iterator[tuple[Window, Area]]:
    assert context
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != area_type:
                continue
            yield (window, area)


def get_sequencer_context(context: Context) -> dict:
    """Context needed for sequencer ops (visible sequencer is needed)"""
    areas = list(find_areas_by_type(context, 'SEQUENCE_EDITOR'))
    if not areas:
        return {}
    (window, area) = areas[0]
    return {
        "window": window,
        "screen": window.screen,
        "area": area,
        "scene": context.scene,
    }


def assert_op_ret(ret: set[str]):
    assert 'FINISHED' in ret, f"Operation execution failed with {ret} code"


def draw_expandable_header(props: Any, property_name: str, label: str, layout: UILayout, errors=False) -> bool:
    """Draws a checkbox which looks like collapsable sub-panel's header.
    Expanded/collapsed state is driven by the provided property.
    Returns the expanded status. Inspired by GameRigtTool plugin"""
    assert props and property_name
    row = layout.row(align=True)
    row.alignment = "LEFT"

    expanded = getattr(props, property_name)
    if expanded:
        # icon = 'TRIA_DOWN'
        icon = 'DISCLOSURE_TRI_DOWN'
    else:
        # icon = 'TRIA_RIGHT'
        icon = 'DISCLOSURE_TRI_RIGHT'
        if errors:
            row.alert = True
            icon = "ERROR"

    row.prop(props, property_name, text=label, emboss=False, icon=icon)

    return expanded


def draw_prop_with_label(props: Any, property_name: str, label, layout: UILayout):
    col = layout.column()
    split = col.split(factor=0.229)
    split.alignment = 'LEFT'
    split.label(text=label)
    split.prop(props, property_name, text="")


def draw_error(layout, msg: str):
    box = layout.box()
    box.alert = True
    lines = msg.splitlines()
    if not lines:
        lines = [""]
    if len(lines) == 1:  # Single line

        box.label(text=msg, icon="ERROR")
        return
    # Multiline
    box.label(text="", icon="ERROR")
    for l in lines:
        box.label(text=l, icon="BLANK1")


def to_relative_path(blender_path: str) -> str:
    if not blender_path:
        return ""
    try:  # Can fail on windows
        return bpy.path.relpath(blender_path)
    except ValueError:
        return blender_path  # Keep unchanged


def to_abs_path(blender_path: str) -> str:
    if not blender_path:
        return ""
    return bpy.path.abspath(blender_path)


def validation_poll(cls: Type, context: Context, disabled_reason: Callable[[Context], str] = None) -> bool:
    assert cls
    if not disabled_reason:  # Locate the 'disabled_reason' as the validation fn if no one is provided
        assert hasattr(cls, 'disabled_reason'), f"No validation function provided and the {cls} has no 'disabled_reason' class method"
        disabled_reason = cls.disabled_reason
    ret = disabled_reason(context)
    if not ret:  # No validation errors
        return True
    # Following is not a class method per doc. But seems to work like it
    cls.poll_message_set(ret)  # type: ignore
    return False
