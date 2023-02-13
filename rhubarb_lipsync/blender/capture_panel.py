import logging
import pathlib
from io import TextIOWrapper
from typing import Dict, List, Optional, cast

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Context, Sound, SoundSequence

import rhubarb_lipsync.blender.rhubarb_operators as rhubarb_operators
import rhubarb_lipsync.blender.sound_operators as sound_operators
import rhubarb_lipsync.blender.ui_utils as ui_utils
from rhubarb_lipsync.blender.preferences import RhubarbAddonPreferences
from rhubarb_lipsync.blender.properties import CaptureProperties, MouthCueList
from rhubarb_lipsync.blender.ui_utils import IconsManager
from rhubarb_lipsync.blender.cue_list import MouthCueUIList
from rhubarb_lipsync.rhubarb.rhubarb_command import RhubarbCommandAsyncJob

log = logging.getLogger(__name__)


class CaptureMouthCuesPanel(bpy.types.Panel):

    bl_idname = "RLPS_PT_capture_panel"
    bl_label = "RLPS: Sound setup and cues capture"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RLSP"
    # bl_parent_id= 'VIEW3D_PT_example_panel'
    # bl_description = "Tool tip"
    # bl_context = "object"

    def draw_sound_setup(self) -> bool:
        props = CaptureProperties.from_context(self.ctx)
        prefs = RhubarbAddonPreferences.from_context(self.ctx)
        sound: Sound = props.sound

        # Redundant validations to allow collapsing this sub-panel while still indicating any errors
        if sound is None:
            errors = True
        else:
            path = pathlib.Path(sound.filepath)
            errors = sound.packed_file or not path.exists or not props.is_sound_format_supported()
        if not ui_utils.draw_expandable_header(prefs, "sound_source_panel_expanded", "Input sound setup", self.layout, errors):
            return not errors

        layout = self.layout
        layout.template_ID(props, "sound", open="sound.open")  # type: ignore
        if sound is None:
            ui_utils.draw_error(self.layout, "Select a sound file.")
            return False
        row = layout.row(align=True)
        row.prop(sound, "filepath", text="")  # type: ignore

        blid = sound_operators.ToggleRelativePath.bl_idname

        op = row.operator(blid, text="", icon="DOT").relative = True
        op = row.operator(blid, text="", icon="ITALIC").relative = False

        row = layout.row(align=True)
        row.operator(sound_operators.CreateSoundStripWithSound.bl_idname, icon='SPEAKER')
        row.operator(sound_operators.RemoveSoundStripWithSound.bl_idname, icon='MUTE_IPO_OFF')
        layout.prop(self.ctx.scene, 'use_audio_scrub')
        if sound:
            layout.prop(sound, "use_memory_cache")

        if sound.packed_file:
            ui_utils.draw_error(self.layout, "Rhubarb requires the file on disk.\n Please unpack the sound.")
            unpackop = layout.operator("sound.unpack", icon='PACKAGE', text=f"Unpack '{sound.name}'")
            unpackop.id = sound.name_full  # type: ignore
            unpackop.method = 'USE_ORIGINAL'  # type: ignore
            return False

        if not path.exists:
            ui_utils.draw_error(self.layout, "Sound file doesn't exist.")
            return False

        convert = False

        if sound.samplerate < 16 * 1000:
            ui_utils.draw_error(self.layout, "Only samplerate >16k supported")
            convert = True

        if not props.is_sound_format_supported():
            ui_utils.draw_error(self.layout, "Only wav or ogg supported.")
            convert = True

        if convert or prefs.always_show_conver:
            row = layout.row(align=True)
            row.label(text="Convert to")
            blid = sound_operators.ConvertSoundFromat.bl_idname

            op = row.operator(blid, text="ogg")
            op.codec = 'ogg'  # type: ignore
            sound_operators.ConvertSoundFromat.init_props_from_sound(op, self.ctx)

            op = row.operator(blid, text="wav")
            op.codec = 'wav'  # type: ignore
            sound_operators.ConvertSoundFromat.init_props_from_sound(op, self.ctx)

            return False

        return True

    def draw_info(self) -> None:
        props = CaptureProperties.from_context(self.ctx)
        prefs = RhubarbAddonPreferences.from_context(self.ctx)
        sound: Sound = props.sound
        if not ui_utils.draw_expandable_header(prefs, "info_panel_expanded", "Additional info", self.layout):
            return
        box = self.layout.box().column(align=True)
        # line = layout.split()
        if sound:
            line = box.split()
            line.label(text="Sample rate")
            line.label(text=f"{sound.samplerate} Hz")
            line = box.split()
            line.label(text="Channels")
            line.label(text=str(sound.channels))

            line = box.split()
            line.label(text="File extension")
            line.label(text=props.sound_file_extension)
            box.separator()
        line = box.split()
        line.label(text="Rhubarb version")
        ver = rhubarb_operators.GetRhubarbExecutableVersion.get_cached_value(self.ctx)
        if ver:  # Cached value, just show
            line.label(text=ver)
        else:  # Not cached, offer button
            line.operator(rhubarb_operators.GetRhubarbExecutableVersion.bl_idname)

        line = box.split()
        line.label(text="FPS")
        r = self.ctx.scene.render

        line.label(text=f"{r.fps/r.fps_base:0.2f}")

    def get_job_status_title(self, job: Optional[RhubarbCommandAsyncJob]) -> str:
        status = getattr(job, 'status', None)
        if not status:
            return rhubarb_operators.ProcessSoundFile.bl_label
        return f"Capture ({status})"

    def draw_job(self) -> None:
        props = CaptureProperties.from_context(self.ctx)
        layout = self.layout

        job = rhubarb_operators.ProcessSoundFile.get_job(self.ctx)
        title = self.get_job_status_title(job)
        layout.operator(rhubarb_operators.ProcessSoundFile.bl_idname, text=title, icon_value=IconsManager.logo_icon())

        if not job:
            return
        # props.progress = job.last_progress #No allowed
        if props.progress != 100 and props.progress > 0:
            r = layout.row()
            r.enabled = False
            r.prop(props, "progress", text="Progress", slider=True)
        ex = job.last_exception
        if ex:
            ui_utils.draw_error(layout, f"{type(ex).__name__}\n{' '.join(ex.args)}")

    def draw_capture(self) -> None:

        prefs = RhubarbAddonPreferences.from_context(self.ctx)
        job = rhubarb_operators.ProcessSoundFile.get_job(self.ctx)
        title = self.get_job_status_title(job)
        error = getattr(job, 'last_exception', False)

        if not ui_utils.draw_expandable_header(prefs, "caputre_panel_expanded", title, self.layout, error):
            return

        self.draw_job()
        props = CaptureProperties.from_context(self.ctx)

        layout = self.layout
        layout.prop(props, "dialog_file")
        layout.prop(prefs, "use_extended_shapes")

        # row = layout.row()
        lst: MouthCueList = props.cue_list
        layout.template_list(MouthCueUIList.bl_idname, "Mouth cues", lst, "items", lst, "index")
        # layout.template_list(MouthCueUIList.bl_idname, "Mouth cues", lst, "items", lst, "index", type="GRID")

    def draw(self, context: Context):
        try:
            props = CaptureProperties.from_context(context)
            self.ctx = context
            layout = self.layout
            # layout.use_property_split = True
            # layout.use_property_decorate = False  # No animation.

            selection_error = CaptureProperties.context_selection_validation(context)
            if selection_error:
                ui_utils.draw_error(self.layout, selection_error)
            else:
                self.draw_sound_setup()
            self.draw_info()

            self.draw_capture()

        except Exception as e:
            ui_utils.draw_error(self.layout, f"Unexpected error. \n {e}")
            raise
        finally:
            self.ctx = None  # type: ignore
