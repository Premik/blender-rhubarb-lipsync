import logging
from functools import cached_property
from types import ModuleType
from typing import Dict, List, Optional, cast
import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty, BoolProperty
from bpy.types import Context, Object, UILayout, NlaTrack
from typing import Any, Callable, Optional, cast, Generator, Iterator

from rhubarb_lipsync.blender.capture_properties import CaptureListProperties, CaptureProperties, MouthCueList, MouthCueListItem
from rhubarb_lipsync.blender.mapping_properties import MappingProperties, MappingItem, NlaTrackRef
from rhubarb_lipsync.blender.preferences import CueListPreferences, RhubarbAddonPreferences, MappingPreferences
from rhubarb_lipsync.rhubarb.log_manager import logManager
from rhubarb_lipsync.rhubarb.mouth_shape_data import MouthCue, MouthShapeInfos, MouthShapeInfo
import rhubarb_lipsync.blender.ui_utils as ui_utils
import traceback
from rhubarb_lipsync.blender.ui_utils import IconsManager

log = logging.getLogger(__name__)


def objects_with_mapping(objects: Iterator[Object]) -> Generator[Object | Any, Any, None]:
    """Filter all objects which non-blank mapping properties"""
    for o in objects or []:
        mp = MappingProperties.from_object(o)
        if mp and mp.has_any_mapping:
            yield o


class BakingContext:
    """Ease navigation and iteration over various stuff needed for baking"""

    def __init__(self, ctx: Context) -> None:
        assert ctx
        self.ctx = ctx
        self.clear_obj_cache()

    @cached_property
    def prefs(self) -> RhubarbAddonPreferences:
        return RhubarbAddonPreferences.from_context(self.ctx)

    @cached_property
    def mprefs(self) -> MappingPreferences:
        return self.prefs.mapping_prefs

    def clear_obj_cache(self) -> None:
        self._objs: List[Object] = None
        self.object_index = -1
        self.track_index = 0
        self.cue_index = -1
        self.last_object_selection_type = ""

    @property
    def objects(self) -> List[Object]:
        """All objects to bake the cues on."""
        if self.last_object_selection_type != self.mprefs.object_selection_type:
            self.clear_obj_cache()  # Selection type has changed, invalidate cache
            self.last_object_selection_type = self.mprefs.object_selection_type
        if self._objs is None:  # Rebuild obj cache
            obj_sel = self.mprefs.object_selection(self.ctx)
            self._objs = list(objects_with_mapping(obj_sel))
        return self._objs

    def object_iter(self) -> Iterator[Object]:
        for i, o in enumerate(self.objects):
            self.object_index = i
            yield o
        self.object_index = -1

    @property
    def current_object(self) -> Object:
        if self.object_index < 0:
            return None
        if self.object_index >= len(self.objects):
            self.object_index = -1
            return None
        return self.objects[self.object_index]

    def next_object(self) -> Object:
        self.object_index += 1
        return self.current_object

    @cached_property
    def cprops(self) -> CaptureListProperties:
        return CaptureListProperties.capture_from_context(self.ctx)

    @cached_property
    def cue_items(self) -> list[MouthCueListItem]:
        if not self.cprops or not self.cprops.cue_list:
            return []
        cl: MouthCueList = self.cprops.cue_list
        return cl.items

    def cue_iter(self) -> Iterator[MouthCueListItem]:
        for i, c in enumerate(self.cue_items):
            self.cue_index = i
            yield c
        self.cue_index = -1

    @property
    def current_cue(self) -> MouthCueListItem:
        if self.cue_index < 0:
            return None
        if self.cue_index >= len(self.cue_items):
            self.cue_index = -1
            return None
        return self.cue_items[self.cue_index]

    def next_cue(self) -> MouthCueListItem:
        self.cue_index += 1
        return self.current_cue

    @property
    def last_cue(self) -> Optional[MouthCueListItem]:
        if not self.cue_items:
            return None
        return self.cue_items[-1]

    @property
    def mprops(self) -> MappingProperties:
        """Mapping properties of the current object"""
        return MappingProperties.from_object(self.current_object)

    @property
    def track1(self) -> Optional[NlaTrack]:
        trackRef: NlaTrackRef = self.mprops and self.mprops.nla_track1
        return trackRef and trackRef.selected_item(self.ctx)

    @property
    def track2(self) -> Optional[NlaTrack]:
        trackRef: NlaTrackRef = self.mprops and self.mprops.nla_track2
        return trackRef and trackRef.selected_item(self.ctx)

    @property
    def tracks(self) -> List[NlaTrack]:
        """Both tracks of the current object. Some items can be None"""
        return [self.track1, self.track2]

    @property
    def current_track(self) -> NlaTrack:
        if self.track_index < 0:
            return None
        return self.tracks[self.track_index % 2]

    def next_track(self) -> Object:
        """Alternates between non-null tracks. If only one track is non-null it would always the current track"""
        self.track_index += 1
        if not self.current_track:  # Next one is None
            self.track_index += 1  # Try the other one. If None too then both are None
        return self.current_track

    def validate_current_object(self) -> list[str]:
        """Return validation errors of `self.object`."""
        if not self.current_object:
            return ["No object provided for validation"]
        if not self.mprops:
            return ["Object has no mapping properties"]
        if not self.mprops.has_any_mapping:
            return ["Object has no mapping"]

        ret: list[str] = []
        if not self.cue_items:
            ret += ["No cues in the capture"]
        extended: list[str] = []
        if self.prefs.use_extended_shapes:
            extended = [msi.key for msi in MouthShapeInfos.extended()]
        if self.mprops.nla_map_action:  # Find unmapped cues (regular action). Ignore extended if not used
            lst = ','.join([k for k in self.mprops.blank_keys if k not in extended])
            ret += [f"{lst} has no action mapped"]

        if self.mprops.nla_map_shapekey:
            lst = ','.join([k for k in self.mprops.blank_shapekeys if k not in extended])
            ret += [f"{lst} has no shape-action mapped"]

        self.next_track()
        if not self.current_track:
            ret += [f"no NLA track selected"]
        return ret


class BakeToNLA(bpy.types.Operator):
    """Bake the selected objects to nla tracks"""

    bl_idname = "rhubarb.bake_to_nla"
    bl_label = "Bake to NLA"

    @classmethod
    def disabled_reason(cls, context: Context) -> str:
        error_common = CaptureProperties.sound_selection_validation(context, False)
        if error_common:
            return error_common
        error_common = MappingProperties.context_selection_validation(context)
        if error_common:
            return error_common
        props = CaptureListProperties.capture_from_context(context)
        return ""

    @classmethod
    def poll(cls, context: Context) -> bool:
        return ui_utils.validation_poll(cls, context)

    def invoke(self, context: Context, event: bpy.types.Event) -> set[int] | set[str]:
        # Open dialog
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=340)

    def execute(self, ctx: Context) -> set[str]:
        self.bctx = BakingContext(ctx)
        return {'FINISHED'}

    def draw_error_inbox(self, l: UILayout, text: str) -> None:
        l.alert = True
        l.label(text=text, icon="ERROR")

    def draw_info(self) -> None:
        b = self.bctx
        box = self.layout.box().column(align=True)
        line = box.split()
        if b.cprops:
            line.label(text="Capture")
            line.label(text=f"{b.cprops.sound_file_basename}.{b.cprops.sound_file_extension}")
        else:
            ui_utils.draw_error(self.layout, "No capture selected")

        line = box.split()
        line.label(text="Mouth cues")
        if b.cue_items:
            line.label(text=str(len(b.cue_items)))
        else:
            self.draw_error_inbox(line, "No cues")

        line = box.split()
        line.label(text="Objects selected")
        selected_objects = list(b.mprefs.object_selection(b.ctx))
        if selected_objects:
            line.label(text=f"{len(selected_objects)}")
        else:
            self.draw_error_inbox(line, "None")

        objs_to_bake = b.objects
        line = box.split()
        line.label(text="Objects with mapping")
        if len(objs_to_bake):
            line.label(text=f"{len(objs_to_bake)}")
        else:
            self.draw_error_inbox(line, "None of the selected")

    def draw_validation(self) -> None:
        b = self.bctx
        box = self.layout.box().column(align=True)
        for o in b.object_iter():
            errs = b.validate_current_object()

            if errs:
                box.separator()
                row = box.row()
                row.label(text=o.name)

                for e in errs:
                    self.draw_error_inbox(box.row(), e)

    def draw(self, ctx: Context) -> None:
        self.bctx = BakingContext(ctx)

        layout = self.layout
        row = layout.row(align=False)
        row.prop(self.bctx.cprops, "start_frame")
        if self.bctx.last_cue:
            row.label(text=f"End frame: {self.bctx.last_cue.end_frame_str(ctx)}")
        layout.prop(self.bctx.mprefs, "object_selection_type")
        self.draw_info()
        self.draw_validation()
        # ui_utils.draw_prop_with_label(m, "rate", "Rate", layout)
