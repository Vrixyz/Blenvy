import json
import os
from types import SimpleNamespace
import bpy

from bpy.types import (PropertyGroup)
from bpy.props import (PointerProperty, IntProperty, StringProperty)

from .did_export_settings_change import did_export_settings_change
from .get_collections_to_export import get_collections_to_export

from ..constants import TEMPSCENE_PREFIX
from .internals import CollectionsToExport
from ..helpers.helpers_scenes import (get_scenes)
from ..helpers.helpers_collections import (get_exportable_collections)
from .preferences import AutoExportGltfAddonPreferences

class AutoExportTracker(PropertyGroup):

    changed_objects_per_scene = {}
    change_detection_enabled = True
    export_params_changed = False

    gltf_settings_backup = None
    last_operator = None
    dummy_file_path = ""

    exports_total : IntProperty(
        name='exports_total',
        description='Number of total exports',
        default=0
    ) # type: ignore

    exports_count : IntProperty(
        name='exports_count',
        description='Number of exports in progress',
        default=0
    ) # type: ignore

    @classmethod
    def register(cls):
        bpy.types.WindowManager.auto_export_tracker = PointerProperty(type=AutoExportTracker)
        # register list of exportable collections
        bpy.types.WindowManager.exportedCollections = bpy.props.CollectionProperty(type=CollectionsToExport)

        # setup handlers for updates & saving
        #bpy.app.handlers.save_post.append(cls.save_handler)
        #bpy.app.handlers.depsgraph_update_post.append(cls.deps_update_handler)

    @classmethod
    def unregister(cls):
        # remove handlers & co
        """try:
            bpy.app.handlers.depsgraph_update_post.remove(cls.deps_update_handler)
        except:pass
        try:
            bpy.app.handlers.save_post.remove(cls.save_handler)
        except:pass"""
        del bpy.types.WindowManager.auto_export_tracker
        del bpy.types.WindowManager.exportedCollections

    @classmethod
    def save_handler(cls, scene, depsgraph):
        print("-------------")
        print("saved", bpy.data.filepath)
        # auto_export(changes_per_scene, export_parameters_changed)
        bpy.ops.export_scenes.auto_gltf(direct_mode= True)

        # (re)set a few things after exporting
        # reset wether the gltf export paramters were changed since the last save 
        cls.export_params_changed = False
        # reset whether there have been changed objects since the last save 
        cls.changed_objects_per_scene.clear()
        # all our logic is done, mark this as done

    @classmethod
    def deps_update_handler(cls, scene, depsgraph):
        # print("change detection enabled", cls.change_detection_enabled)

        """ops = bpy.context.window_manager.operators
        print("last operators", ops)
        for op in ops:
            print("operator", op)"""
        active_operator = bpy.context.active_operator
        if active_operator:
            #print("Operator", active_operator.bl_label, active_operator.bl_idname)
            if active_operator.bl_idname == "EXPORT_SCENE_OT_gltf" and active_operator.gltf_export_id == "gltf_auto_export":
                # we backup any existing gltf export settings, if there were any
                scene = bpy.context.scene
                if "glTF2ExportSettings" in scene:
                    existing_setting = scene["glTF2ExportSettings"]
                    bpy.context.window_manager.gltf_settings_backup = json.dumps(dict(existing_setting))

                # we force saving params
                active_operator.will_save_settings = True
                # we set the last operator here so we can clear the specific settings (yeah for overly complex logic)
                cls.last_operator = active_operator
                #print("active_operator", active_operator.has_active_exporter_extensions, active_operator.__annotations__.keys(), active_operator.filepath, active_operator.gltf_export_id)
            if active_operator.bl_idname == "EXPORT_SCENES_OT_auto_gltf":
                # we force saving params
                active_operator.will_save_settings = True
                active_operator.auto_export = True
                print("setting stuff for auto_export")

        # only deal with changes if we are NOT in the mids of saving/exporting
        if cls.change_detection_enabled:
            # ignore anything going on with temporary scenes
            if not scene.name.startswith(TEMPSCENE_PREFIX):
                # print("depsgraph_update_post", scene.name)
                changed_scene = scene.name or ""
                #print("-------------")
                if not changed_scene in cls.changed_objects_per_scene:
                    cls.changed_objects_per_scene[changed_scene] = {}
                # print("cls.changed_objects_per_scene", cls.changed_objects_per_scene)
                # depsgraph = bpy.context.evaluated_depsgraph_get()
                for obj in depsgraph.updates:
                    #print("depsgraph update", obj)
                    if isinstance(obj.id, bpy.types.Object):
                        # get the actual object
                        object = bpy.data.objects[obj.id.name]
                        print("  changed object", obj.id.name, "changes", obj, "transforms", obj.is_updated_transform, "geometry", obj.is_updated_geometry)
                        cls.changed_objects_per_scene[scene.name][obj.id.name] = object
                    elif isinstance(obj.id, bpy.types.Material): # or isinstance(obj.id, bpy.types.ShaderNodeTree):
                        # print("  changed material", obj.id, "scene", scene.name,)
                        material = bpy.data.materials[obj.id.name]
                        #now find which objects are using the material
                        for obj in bpy.data.objects:
                            for slot in obj.material_slots:
                                if slot.material == material:
                                    cls.changed_objects_per_scene[scene.name][obj.name] = obj

                items = 0
                for scene_name in cls.changed_objects_per_scene:
                    items += len(cls.changed_objects_per_scene[scene_name].keys())
                if items == 0:
                    cls.changed_objects_per_scene.clear()
                # print("changed_objects_per_scene", cls.changed_objects_per_scene)
        else:
            cls.changed_objects_per_scene.clear()


        # get a list of exportable collections for display
        # keep it simple, just use Simplenamespace for compatibility with the rest of our code
        # TODO: debounce

        export_settings_changed = did_export_settings_change()
        tmp = {}
        for k in AutoExportGltfAddonPreferences.__annotations__:
            item = AutoExportGltfAddonPreferences.__annotations__[k]
            default = item.keywords.get('default', None)
            tmp[k] = default
        auto_settings = get_auto_exporter_settings()
        for k in auto_settings:
            tmp[k] = auto_settings[k]
        tmp['__annotations__'] = tmp

        # path to the current blend file
        file_path = bpy.data.filepath
        # Get the folder
        folder_path = os.path.dirname(file_path)
        export_output_folder =tmp["export_output_folder"]
        export_models_path = os.path.join(folder_path, export_output_folder)
        export_blueprints_path = os.path.join(folder_path, export_output_folder, tmp["export_blueprints_path"]) if tmp["export_blueprints_path"] != '' else folder_path
        tmp["export_blueprints_path"] = export_blueprints_path
        tmp["export_models_path"] = export_models_path
        addon_prefs = SimpleNamespace(**tmp)

        (collections, collections_to_export, library_collections, collections_per_scene) = get_collections_to_export(cls.changed_objects_per_scene, export_settings_changed, addon_prefs)
        print("collections to export", collections_to_export)
        try:
            # we save this list of collections in the context
            bpy.context.window_manager.exportedCollections.clear()
            #TODO: add error handling for this
            for collection_name in collections_to_export:
                ui_info = bpy.context.window_manager.exportedCollections.add()
                ui_info.name = collection_name
        except Exception as error:
            pass
            #self.report({"ERROR"}, "Failed to populate list of exported collections/blueprints")
            
        """depsgraph = bpy.context.evaluated_depsgraph_get()
        for update in depsgraph.updates:
            print("update", update)"""

    def disable_change_detection(self):
        #print("disable change detection")
        self.change_detection_enabled = False
        self.__class__.change_detection_enabled = False
        return None
    
    def enable_change_detection(self):
        #print("enable change detection")
        self.change_detection_enabled = True
        self.__class__.change_detection_enabled = True
        #print("bpy.context.window_manager.auto_export_tracker.change_detection_enabled", bpy.context.window_manager.auto_export_tracker.change_detection_enabled)
        return None
    
    def clear_changes(self):
        self.changed_objects_per_scene.clear()
        self.__class__.changed_objects_per_scene.clear()

    def export_finished(self):
        #print("export_finished")
        self.exports_count -= 1
        if self.exports_count == 0:
            print("preparing to reset change detection")
            bpy.app.timers.register(self.enable_change_detection, first_interval=0.1)
            #self.enable_change_detection()
        return None


def get_auto_exporter_settings():
    auto_exporter_settings = bpy.data.texts[".gltf_auto_export_settings"] if ".gltf_auto_export_settings" in bpy.data.texts else None
    if auto_exporter_settings != None:
        try:
            auto_exporter_settings = json.loads(auto_exporter_settings.as_string())
        except:
            auto_exporter_settings = {}
    else:
        auto_exporter_settings = {}
    
    return auto_exporter_settings