import bpy
import os
import urllib.request
import tempfile
import ssl
import shutil

version_number = "1.0.3"
platform = 'Linux' #macOs Windows
zip_name=f"rhubarb_lipsync_ng-{platform}-{version_number}.zip"

# GitHub release URL
github_release_url = f"https://github.com/Premik/blender_rhubarb_lipsync_ng/releases/download/v{version_number}/{zip_name}"


# Create a temporary directory
temp_dir = os.path.join(tempfile.gettempdir(), 'blender_rhubarb_temp')
os.makedirs(temp_dir, exist_ok=True)
# Full path for the downloaded zip file
addon_zip_path = os.path.join(temp_dir, zip_name)

if not os.path.isfile(addon_zip_path):
    print(f"Downloading {github_release_url}")
    ssl_context = ssl._create_unverified_context()
    #urllib.request.urlretrieve(github_release_url, addon_zip_path)
    #urllib.request.urlretrieve(github_release_url, addon_zip_path)    
    with urllib.request.urlopen(github_release_url, context=ssl_context) as response, open(addon_zip_path, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)
     
else:
    print(f"File already exists: {addon_zip_path}")

print(f"Installing {addon_zip_path}")
bpy.ops.preferences.addon_install(overwrite=True, filepath=addon_zip_path)

print("Doing smoke tests.")
print("\033[93m" + "-" * 50 + "\033[0m")
bpy.ops.preferences.addon_enable(module='rhubarb_lipsync')
print(bpy.ops.rhubarb.get_executable_version())
print(bpy.ops.rhubarb.create_capture_props())
#print(bpy.ops.rhubarb.process_sound_file()) # No sound file selected

# Run:
#blender --background --python adhoc-install.py