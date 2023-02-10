bl_info = {
    'name': 'Rhubarb Lipsync',
    'author': 'Addon rewritten by Premysl S. base on the original version by Andrew Charlton. Includes Rhubarb Lip Sync by Daniel S. Wolf',
    'version': (4, 0, 0),
    'blender': (3, 40, 0),
    'location': 'Properties > Armature',
    'description': 'Integrate Rhubarb Lipsync into Blender',
    'wiki_url': 'https://github.com/Premik/blender-rhubarb-lipsync',
    'tracker_url': 'https://github.com/Premik/blender-rhubarb-lipsync/issues',
    'support': 'COMMUNITY',
    'category': 'Animation',
}


import bpy
from bpy.props import PointerProperty
from rhubarb_lipsync.blender.properties import CaptureProperties
from rhubarb_lipsync.blender.preferences import RhubarbAddonPreferences
from rhubarb_lipsync.blender.ui_utils import IconsManager
from rhubarb_lipsync.rhubarb.log_manager import logManager
import rhubarb_lipsync.blender.auto_load


def init_loggers():
    logManager.init(rhubarb_lipsync.blender.auto_load.modules)
    prefs = RhubarbAddonPreferences.from_context(bpy.context, False)
    if hasattr(prefs, 'log_level') and prefs.log_level != 0:  # 0 default level
        logManager.set_level(prefs.log_level)


# print(f"FILE:  {__file__}")
rhubarb_lipsync.blender.auto_load.init(__file__)


def register():
    rhubarb_lipsync.blender.auto_load.register()
    bpy.types.Object.rhubarb_lipsync = PointerProperty(type=CaptureProperties)
    init_loggers()


def unregister():
    rhubarb_lipsync.blender.auto_load.unregister()
    del bpy.types.Object.rhubarb_lipsync

    IconsManager.unregister()


# bpy.utils.register_classes_factory

# from rhubarb_lipsync.blender.testing_panel import ExamplePanel, TestOpOperator
# from rhubarb_lipsync.blender.properties import LipsyncProperties

# register2, unregister = bpy.utils.register_classes_factory([LipsyncProperties, ExamplePanel, TestOpOperator])

# from bpy.props import FloatProperty, StringProperty, BoolProperty, PointerProperty
# def register():
#    register2()
#    bpy.types.Object.rhubarb_lipsync=PointerProperty(type=LipsyncProperties)
