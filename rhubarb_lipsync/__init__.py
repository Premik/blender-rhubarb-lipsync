print("RLSP: enter __init__")
from typing import Optional

import bpy
from bpy.props import PointerProperty


from .blender.auto_load import AutoLoader
from .blender.capture_properties import CaptureListProperties
from .blender.mapping_properties import MappingProperties
from .blender.preferences import RhubarbAddonPreferences
from .blender.ui_utils import IconsManager
from .rhubarb.log_manager import logManager

bl_info = {
    'name': 'Rhubarb Lipsync NG',
    'author': 'Premysl Srubar. Inspired by the original version by Andrew Charlton. Includes Rhubarb Lip Sync by Daniel S. Wolf',
    'version': (1, 5, 0),
    'blender': (4, 0, 2),
    'location': '3d View > Sidebar',
    'description': 'Integrate Rhubarb Lipsync into Blender',
    'wiki_url': 'https://github.com/Premik/blender_rhubarb_lipsync_ng',
    'tracker_url': 'https://github.com/Premik/blender_rhubarb_lipsync_ng/issues',
    'support': 'COMMUNITY',
    'category': 'Animation',
}

autoloader: Optional[AutoLoader]


def is_blender_in_debug() -> bool:
    '''Whether Blender was started with --debug or --debug-python flags'''
    return bpy.app.debug or bpy.app.debug_python


def init_loggers(prefs: Optional[RhubarbAddonPreferences]) -> None:
    global autoloader
    if is_blender_in_debug():
        print("RLPS: enter init_loggers() ")
    logManager.init(autoloader.modules)

    if is_blender_in_debug():  # If Blender is in debug, force TRACE loglevel
        logManager.set_trace()
        print(f"RLPS Set TRACE level for {len(logManager.logs)} loggers")
        logManager.ensure_console_handler()
    else:
        if hasattr(prefs, 'log_level') and prefs.log_level != 0:  # 0 default level
            logManager.set_level(prefs.log_level)


# print(f"FILE:  {__file__}")
# if is_blender_in_debug():


def register() -> None:
    global autoloader

    if is_blender_in_debug():
        print("RLPS: enter register() ")
    autoloader = AutoLoader(root=__file__)
    autoloader.register()

    bpy.types.Scene.rhubarb_lipsync_captures = PointerProperty(type=CaptureListProperties)
    bpy.types.Object.rhubarb_lipsync_mapping = PointerProperty(
        type=MappingProperties,
        options={'LIBRARY_EDITABLE'},
        override={'LIBRARY_OVERRIDABLE'},
    )

    prefs = RhubarbAddonPreferences.from_context(bpy.context, False)
    init_loggers(prefs)
    if hasattr(prefs, 'capture_tab_name'):  # Re-set the tab names in case they differ from defaults
        prefs.capture_tab_name_updated(bpy.context)
        prefs.map_tab_name_updated(bpy.context)
    if is_blender_in_debug():
        print("RLPS: exit register() ")


def unregister() -> None:
    global autoloader
    IconsManager.unregister()
    # if 'logManager' in globals():
    #     global logManager
    #     del logManager
    autoloader.unregister()
    del bpy.types.Scene.rhubarb_lipsync_captures
    del bpy.types.Object.rhubarb_lipsync_mapping


# bpy.utils.register_classes_factory

# from rhubarb_lipsync.blender.testing_panel import ExamplePanel, TestOpOperator
# from rhubarb_lipsync.blender.capture_properties import LipsyncProperties

# register2, unregister = bpy.utils.register_classes_factory([LipsyncProperties, ExamplePanel, TestOpOperator])

# from bpy.props import FloatProperty, StringProperty, BoolProperty, PointerProperty
# def register():
#    register2()
#    bpy.types.Object.rhubarb_lipsync=PointerProperty(type=LipsyncProperties)

print("RLSP: exit __init__")
