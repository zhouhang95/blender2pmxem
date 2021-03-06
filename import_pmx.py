import bpy
import mathutils
from mathutils import Vector
import os
import math
import re

from . import add_function, global_variable
from bpy_extras.node_shader_utils import PrincipledBSDFWrapper

from .pmx import pmx
from .pmx.pmx import PMMorph
from .pmx.pmx import PMMaterial
from .pmx.pmx import PMTexture
from .pmx.pmx import PMMorphOffset

from typing import List
from typing import Dict
from typing import Iterable
from typing import Generator
from typing import Tuple

# global_variable
GV = global_variable.Init()


def convert_translate(vec):  # GlobalTransformation
    w = vec * 0.08
    w = w.xzy
    return w


def convert_normal(vec):  # GlobalTransformation
    w = vec.xzy
    return w


def Get_JP_or_EN_Name(jp_name, en_name, use_japanese_name, bone_mode=False):
    tmp_name = jp_name

    if (not use_japanese_name) and en_name != "":
        tmp_name = en_name

    if bone_mode:
        findR = re.compile("\u53f3")
        findL = re.compile("\u5de6")

        if findR.search(tmp_name):
            tmp_name = findR.sub("", tmp_name) + "_R"

        elif findL.search(tmp_name):
            tmp_name = findL.sub("", tmp_name) + "_L"

    return tmp_name


def Search_Eyes(bone_name):
    return bone_name in ["eyes", "両目"]


def is_tweak_control(bone_name):
    return 'upper_arm_tweak.' in bone_name or 'forearm_tweak.' in bone_name


def Search_Twist_Num(bone_name):
    # 腕捩 \u8155\u6369
    # 手捩 \u624B\u6369
    name_jp = re.search(r'^(\u8155|\u624B)\u6369[0-9]+', bone_name) is not None
    name_en = re.search(r'^(arm|wrist)\s+twist[0-9]+', bone_name) is not None
    return (name_jp or name_en)


def Search_Leg_Dummy(bone_name):
    # 足 \u8DB3
    # ひざ \u3072\u3056
    # 足首 \u8DB3\u9996
    name_jp = re.search(r'^(\u8DB3|\u3072\u3056|\u8DB3\u9996)D', bone_name) is not None
    name_en = re.search(r'(\.|_)(L|R)D$', bone_name) is not None
    return (name_jp or name_en)


def Set_Bone_Position(pmx_data, arm_dat, blender_bone_list, fix=False):
    bone_id = {}

    for (bone_index, data_bone) in enumerate(pmx_data.Bones):
        bone_name = blender_bone_list[bone_index]

        # find tip bone
        if data_bone.Visible == 0 and data_bone.AdditionalRotation == 0 and data_bone.AdditionalMovement == 0:
            tip_type1 = (data_bone.ToConnectType == 0 and data_bone.TailPosition == mathutils.Vector((0, 0, 0)))
            tip_type2 = (data_bone.ToConnectType == 1 and data_bone.ChildIndex <= 0)

            if tip_type1 or tip_type2:
                parent_id = bone_id.get(blender_bone_list.get(data_bone.Parent), -1)
                bone_id[bone_name] = parent_id
                continue

        eb = None
        if fix:
            eb = arm_dat.edit_bones.get(bone_name)
            if eb is None:
                continue

        else:
            eb = arm_dat.edit_bones.new(bone_name)

        eb.head = convert_translate(data_bone.Position)
        eb.roll = 0
        # eb.hide = (data_bone.Visible == 0)
        eb.use_connect = False

        bone_id[bone_name] = bone_name
        fixed_axis = None

        if data_bone.Parent != -1:
            parent_id = bone_id.get(blender_bone_list.get(data_bone.Parent), -1)

            if parent_id != -1:
                parent_bone = arm_dat.edit_bones[parent_id]
                eb.parent = parent_bone
                fixed_axis = (parent_bone.tail - parent_bone.head) * 0.1

                if pmx_data.Bones[data_bone.Parent].ChildIndex == bone_index:
                    if data_bone.Movable == 0 and eb.head != eb.parent.head:
                        eb.use_connect = True

        # Set TailPosition
        if data_bone.ToConnectType == 0:
            eb.tail = convert_translate(data_bone.Position + data_bone.TailPosition)

        elif data_bone.ChildIndex != -1:
            eb.tail = convert_translate(pmx_data.Bones[data_bone.ChildIndex].Position)

        else:
            eb.tail = convert_translate(data_bone.Position + mathutils.Vector((0, 0, 1.0)))

        if data_bone.UseFixedAxis == 1 and eb.head == eb.tail:
            if fixed_axis is None:
                eb.tail = convert_translate(data_bone.Position + data_bone.FixedAxis)
            else:
                eb.tail = eb.head + fixed_axis

        if eb.head == eb.tail:
            if data_bone.AdditionalBoneIndex >= 0 and pmx_data.Bones[data_bone.AdditionalBoneIndex].UseFixedAxis == 1:
                if fixed_axis is None:
                    eb.tail = convert_translate(data_bone.Position +
                                 pmx_data.Bones[data_bone.AdditionalBoneIndex].FixedAxis)
                else:
                    eb.tail = eb.head + fixed_axis
            else:
                eb.tail = convert_translate(data_bone.Position + mathutils.Vector((0, 0, 1.0)))

    return bone_id


def read_pmx_data(context, filepath="",
                  adjust_bone_position=False,
                  bone_transfer=False,
                  ):

    prefs = context.preferences.addons[GV.FolderName].preferences
    use_japanese_name = prefs.use_japanese_name

    GV.SetStartTime()

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')

    if bpy.ops.object.select_all.poll():
        bpy.ops.object.select_all(action='DESELECT')

    pmx_data = pmx.Model()
    with open(filepath, "rb") as f:
        pmx_data.Load(f)

    scene = context.scene
    base_path = os.path.dirname(filepath)

    for ob in scene.objects:
        ob.select_set(False)

    tmp_name = Get_JP_or_EN_Name(pmx_data.Name, pmx_data.Name_E, use_japanese_name)

    arm_dat = bpy.data.armatures.new(tmp_name + "_Arm")
    arm_obj = bpy.data.objects.new(tmp_name + "_Arm", arm_dat)

    arm_obj.show_in_front = True
    arm_dat.display_type = "STICK"

    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.context.view_layer.update()

    blender_bone_list = {
        bone_index: pmx_bone.Name_E for (bone_index, pmx_bone) in enumerate(pmx_data.Bones)
    }

    arm_obj.select_set(True)

    # Set Bone Position
    bpy.ops.object.mode_set(mode="EDIT", toggle=False)
    bone_id = Set_Bone_Position(pmx_data, arm_dat, blender_bone_list)
    add_ik_pole(arm_dat)

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode="POSE", toggle=False)

    set_bone_status(context, pmx_data, arm_obj, arm_dat, blender_bone_list, prefs)
    set_ik_bone(pmx_data, arm_obj, blender_bone_list)

    bpy.ops.object.mode_set(mode="EDIT", toggle=False)


    # BoneItem Direction
    bpy.ops.armature.select_all(action='SELECT')
    bpy.ops.b2pmxem.calculate_roll()
    bpy.ops.armature.select_all(action='DESELECT')

    bpy.ops.object.mode_set(mode='OBJECT')

    # Create Mash
    mesh = bpy.data.meshes.new(tmp_name)
    obj_mesh = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.collection.objects.link(obj_mesh)

    # Link Parent
    mod = obj_mesh.modifiers.new('RigModif', 'ARMATURE')
    mod.object = arm_obj
    mod.use_bone_envelopes = False
    mod.use_vertex_groups = True

    vert_group, vert_group_index = add_vertex_group(pmx_data, mesh, obj_mesh, arm_dat, blender_bone_list, bone_id)
    add_vertex(pmx_data, mesh, vert_group, vert_group_index)
    add_face(pmx_data, mesh)

    if bone_transfer:
        context.view_layer.update()
        return arm_obj, obj_mesh

    textures_dic = add_textures(pmx_data, mesh, base_path)
    mat_status = add_material(pmx_data, mesh, use_japanese_name, textures_dic)
    set_material_and_uv(pmx_data, mesh, mat_status)
    add_shape_key(pmx_data, mesh, obj_mesh, use_japanese_name)

    bpy.context.view_layer.update()

    GV.SetVertCount(len(pmx_data.Vertices))
    GV.PrintTime(filepath, type='import')

def add_ik_pole(arm_dat):
    for lr in ['L', 'R']:
        foot_ik_pole = arm_dat.edit_bones.new('foot_ik_pole.{}'.format(lr))
        foot_ik = arm_dat.edit_bones.get('foot_ik.{}'.format(lr))
        foot_ik_pole.head = foot_ik.head + Vector((0, -1, 0.5))
        foot_ik_pole.tail = foot_ik.head + Vector((0, -1, 0.6))
        foot_ik_pole.parent = foot_ik

def set_ik_bone(pmx_data, arm_obj, blender_bone_list):
    for (bone_index, data_bone) in enumerate(pmx_data.Bones):
        bone_name = blender_bone_list[bone_index]
        pb = arm_obj.pose.bones.get(bone_name)
        # Set IK
        if data_bone.UseIK == False:
            continue
        pb["IKLoops"] = data_bone.IK.Loops
        pb["IKLimit"] = data_bone.IK.Limit

        if len(data_bone.IK.Member) > 0:
            ik_name = blender_bone_list[data_bone.IK.Member[0].Index]
            new_ik = arm_obj.pose.bones[ik_name].constraints.new("IK")
            new_ik.target = arm_obj
            new_ik.subtarget = blender_bone_list[bone_index]
            new_ik.chain_count = len(data_bone.IK.Member)

        for ik_member in data_bone.IK.Member:
            if ik_member.UseLimit != 1:
                continue
            member_name = blender_bone_list[ik_member.Index]
            pose_member = arm_obj.pose.bones[member_name]

            if ik_member.UpperLimit.x == ik_member.LowerLimit.x:
                pose_member.lock_ik_x = True

            else:
                pose_member.use_ik_limit_x = True
                pose_member.ik_min_x = ik_member.LowerLimit.x
                pose_member.ik_max_x = ik_member.UpperLimit.x

            if ik_member.UpperLimit.y == ik_member.LowerLimit.y:
                pose_member.lock_ik_y = True

            else:
                pose_member.use_ik_limit_y = True
                pose_member.ik_min_y = ik_member.LowerLimit.y
                pose_member.ik_max_y = ik_member.UpperLimit.y

            if ik_member.UpperLimit.z == ik_member.LowerLimit.z:
                pose_member.lock_ik_z = True

            else:
                pose_member.use_ik_limit_z = True
                pose_member.ik_min_z = ik_member.LowerLimit.z
                pose_member.ik_max_z = ik_member.UpperLimit.z

    for lr in ['L', 'R']:
        shin = bpy.context.object.pose.bones["shin." + lr]
        shin.constraints["IK"].pole_target = arm_obj
        shin.constraints["IK"].pole_subtarget = "foot_ik_pole." + lr
        shin.constraints["IK"].pole_angle = 1.5708

def set_bone_status(context, pmx_data, arm_obj, arm_dat, blender_bone_list, prefs):
    for (bone_index, data_bone) in enumerate(pmx_data.Bones):
        bone_name = blender_bone_list[bone_index]

        pb = arm_obj.pose.bones.get(bone_name)
        if pb is None:
            continue

        # Find name (True or False)
        find_eyes = Search_Eyes(bone_name)
        find_twist_n = Search_Twist_Num(bone_name)

        if find_twist_n:
            pb.lock_rotation = [True, False, True]

        if data_bone.Rotatable == 0:
            pb.lock_rotation = [True, True, True]

        if data_bone.Movable == 0:
            pb.lock_location = [True, True, True]

        if data_bone.Operational == 0:
            pb.lock_rotation = [True, True, True]
            pb.lock_location = [True, True, True]

        if data_bone.AdditionalRotation == 1:
            const = pb.constraints.new('COPY_ROTATION')
            const.target = arm_obj
            const.subtarget = blender_bone_list[data_bone.AdditionalBoneIndex]
            const.target_space = 'LOCAL'
            const.owner_space = 'LOCAL'

            const.influence = abs(data_bone.AdditionalPower)
            if data_bone.AdditionalPower < 0:
                const.invert_x = True
                const.invert_y = True
                const.invert_z = True

        if data_bone.AdditionalMovement == 1:
            const = pb.constraints.new('COPY_LOCATION')
            const.target = arm_obj
            const.subtarget = blender_bone_list[data_bone.AdditionalBoneIndex]
            const.target_space = 'LOCAL'
            const.owner_space = 'LOCAL'

            const.influence = abs(data_bone.AdditionalPower)
            if data_bone.AdditionalPower < 0:
                const.invert_x = True
                const.invert_y = True
                const.invert_z = True

        if data_bone.UseFixedAxis == 1:
            const = pb.constraints.new('LIMIT_ROTATION')
            const.use_limit_x = True
            const.use_limit_z = True
            const.owner_space = 'LOCAL'
            pb.lock_rotation = [True, False, True]


        # Set Custom Shape
        if prefs.use_custom_shape:
            use_custom_shape(context, pb, bone_name)

def use_custom_shape(context, pb, bone_name):
    find_eyes = Search_Eyes(bone_name)
    find_twist_n = Search_Twist_Num(bone_name)
    len_const = len(pb.constraints)

    if bone_name == 'root':
        add_function.set_custom_shape(context, pb, shape=GV.ShapeMaster)

    elif find_eyes:
        add_function.set_custom_shape(context, pb, shape=GV.ShapeEyes)

    elif is_tweak_control(bone_name) and len_const:
        add_function.set_custom_shape(context, pb, shape=GV.ShapeTwist1)

    elif find_twist_n and len_const:
        add_function.set_custom_shape(context, pb, shape=GV.ShapeTwist2)


def add_vertex_group(pmx_data, mesh, obj_mesh, arm_dat, blender_bone_list, bone_id):
    vert_group = {}
    vert_group_index = {}
    for bone_index, bone_data in enumerate(pmx_data.Bones):
        bone_name = blender_bone_list[bone_index]
        target_name = arm_dat.bones[bone_id[bone_name]].name
        vert_group_index[bone_index] = target_name

        if target_name not in vert_group.keys():
            vert_group[target_name] = obj_mesh.vertex_groups.new(name=target_name)

    mesh.update()
    return vert_group, vert_group_index

def add_vertex(pmx_data, mesh, vert_group, vert_group_index):
    mesh.vertices.add(len(pmx_data.Vertices))

    for vert_index, vert_data in enumerate(pmx_data.Vertices):
        mesh.vertices[vert_index].co = convert_translate(vert_data.Position)
        mesh.vertices[vert_index].normal = convert_normal(vert_data.Normal)
        # mesh.vertices[vert_index].uv = pmx_data.Vertices[vert_index].UV

        # BDEF1
        if vert_data.Type == 0:
            vert_group[vert_group_index[vert_data.Bones[0]]].add([vert_index], 1.0, 'REPLACE')

        # BDEF2
        elif vert_data.Type == 1:
            vert_group[vert_group_index[vert_data.Bones[0]]].add([vert_index], vert_data.Weights[0], 'ADD')
            vert_group[vert_group_index[vert_data.Bones[1]]].add([vert_index], 1.0 - vert_data.Weights[0], 'ADD')

        # BDEF4
        elif vert_data.Type == 2:
            vert_group[vert_group_index[vert_data.Bones[0]]].add([vert_index], vert_data.Weights[0], 'ADD')
            vert_group[vert_group_index[vert_data.Bones[1]]].add([vert_index], vert_data.Weights[1], 'ADD')
            vert_group[vert_group_index[vert_data.Bones[2]]].add([vert_index], vert_data.Weights[2], 'ADD')
            vert_group[vert_group_index[vert_data.Bones[3]]].add([vert_index], vert_data.Weights[3], 'ADD')

        # SDEF
        elif vert_data.Type == 3:
            vert_group[vert_group_index[vert_data.Bones[0]]].add([vert_index], vert_data.Weights[0], 'ADD')
            vert_group[vert_group_index[vert_data.Bones[1]]].add([vert_index], 1.0 - vert_data.Weights[0], 'ADD')
            # Todo? SDEF

        # QDEF
        elif vert_data.Type == 4:
            vert_group[vert_group_index[vert_data.Bones[0]]].add([vert_index], vert_data.Weights[0], 'ADD')
            vert_group[vert_group_index[vert_data.Bones[1]]].add([vert_index], vert_data.Weights[1], 'ADD')
            vert_group[vert_group_index[vert_data.Bones[2]]].add([vert_index], vert_data.Weights[2], 'ADD')
            vert_group[vert_group_index[vert_data.Bones[3]]].add([vert_index], vert_data.Weights[3], 'ADD')
            # Todo? QDEF

    mesh.update()

def add_face(pmx_data, mesh):
    poly_count = len(pmx_data.Faces) // 3
    mesh.polygons.add(poly_count)
    mesh.polygons.foreach_set("loop_start", range(0, poly_count * 3, 3))
    mesh.polygons.foreach_set("loop_total", (3,) * poly_count)
    mesh.polygons.foreach_set("use_smooth", (True,) * poly_count)
    mesh.loops.add(len(pmx_data.Faces))
    # mesh.loops.foreach_set("vertex_index" ,pmx_data.Faces)

    for faceIndex in range(poly_count):
        mesh.loops[faceIndex * 3].vertex_index = pmx_data.Faces[faceIndex * 3]
        mesh.loops[faceIndex * 3 + 1].vertex_index = pmx_data.Faces[faceIndex * 3 + 2]
        mesh.loops[faceIndex * 3 + 2].vertex_index = pmx_data.Faces[faceIndex * 3 + 1]

    mesh.update()

def add_textures(pmx_data, mesh, base_path):
    # image_dic = {}
    textures_dic = {}
    NG_tex_list = []
    for (tex_index, tex_data) in enumerate(pmx_data.Textures):
        tex_path = os.path.join(base_path, tex_data.Path)
        try:
            bpy.ops.image.open(filepath=tex_path)
            # image_dic[tex_index] = bpy.data.images[len(bpy.data.images)-1]
            textures_dic[tex_index] = bpy.data.textures.new(os.path.basename(tex_path), type='IMAGE')
            textures_dic[tex_index].image = bpy.data.images[os.path.basename(tex_path)]

            # Use Alpha
            textures_dic[tex_index].image.alpha_mode = 'PREMUL'

        except RuntimeError:
            NG_tex_list.append(tex_data.Path)

    # print NG_tex_list
    if len(NG_tex_list):
        bpy.ops.b2pmxem.message('INVOKE_DEFAULT',
                                type='INFO',
                                line1="Some Texture file not found.",
                                use_console=True)
        for data in NG_tex_list:
            print("   --> %s" % data)

    mesh.update()
    return textures_dic

def add_material(pmx_data, mesh, use_japanese_name, textures_dic):
    mat_status = []
    for (mat_index, mat_data) in enumerate(pmx_data.Materials):
        blender_mat_name = Get_JP_or_EN_Name(mat_data.Name, mat_data.Name_E, use_japanese_name)

        temp_mattrial = bpy.data.materials.new(blender_mat_name)
        temp_mattrial.use_nodes = True
        temp_principled = PrincipledBSDFWrapper(temp_mattrial, is_readonly=False)
        temp_principled.base_color = mat_data.Deffuse.xyz.to_tuple()
        temp_principled.alpha = mat_data.Deffuse.w

        mat_status.append((len(mat_status), mat_data.FaceLength))

        mesh.materials.append(temp_mattrial)

        # Flags
        # self.Both = 0
        # self.GroundShadow = 1
        # self.DropShadow = 1
        # self.OnShadow = 1
        # self.OnEdge = 1
        #
        # Edge
        # self.EdgeColor =  mathutils.Vector((0,0,0,1))
        # self.EdgeSize = 1.0

        # Texture
        if mat_data.TextureIndex != -1 and mat_data.TextureIndex in textures_dic:
            temp_tex = textures_dic[mat_data.TextureIndex]
            temp_principled.base_color_texture.image = temp_tex.image
            temp_principled.base_color_texture.use_alpha = True
            temp_principled.base_color_texture.texcoords = "UV"

    mesh.update()
    return mat_status

def set_material_and_uv(pmx_data, mesh, mat_status):
    # Set Material & UV
    # Set UV Layer
    if mesh.uv_layers.active_index < 0:
        mesh.uv_layers.new(name="UV_Data")

    mesh.uv_layers.active_index = 0

    uv_data = mesh.uv_layers.active.data[:]

    # uvtex = mesh.uv_textures.new("UV_Data")
    # uv_data = uvtex.data

    index = 0
    for dat in mat_status:
        for i in range(dat[1] // 3):
            # Set Material
            mesh.polygons[index].material_index = dat[0]

            # Set UV
            poly_vert_index = mesh.polygons[index].loop_start
            uv_data[poly_vert_index + 0].uv = pmx_data.Vertices[mesh.polygons[index].vertices[0]].UV
            uv_data[poly_vert_index + 1].uv = pmx_data.Vertices[mesh.polygons[index].vertices[1]].UV
            uv_data[poly_vert_index + 2].uv = pmx_data.Vertices[mesh.polygons[index].vertices[2]].UV

            # Inv UV V
            uv_data[poly_vert_index + 0].uv[1] = 1 - uv_data[poly_vert_index + 0].uv[1]
            uv_data[poly_vert_index + 1].uv[1] = 1 - uv_data[poly_vert_index + 1].uv[1]
            uv_data[poly_vert_index + 2].uv[1] = 1 - uv_data[poly_vert_index + 2].uv[1]

            # TwoSide 2.6 not use?
            # todo set parameter
            # uv_data[index].use_twoside = True

            index = index + 1

    mesh.update()

def add_shape_key(pmx_data, mesh, obj_mesh, use_japanese_name):
    # Add Shape Key
    if len(pmx_data.Morphs) > 0:
        # Add Basis key
        if mesh.shape_keys is None:
            obj_mesh.shape_key_add(name="Basis", from_mix=False)
            mesh.update()

        for data in pmx_data.Morphs:
            # Vertex Morph
            if data.Type == 1:
                blender_morph_name = Get_JP_or_EN_Name(data.Name, data.Name_E, use_japanese_name)
                temp_key = obj_mesh.shape_key_add(name=blender_morph_name, from_mix=False)

                for v in data.Offsets:
                    temp_key.data[v.Index].co += convert_translate(v.Move)

                mesh.update()

        # To activate "Basis" shape
        obj_mesh.active_shape_key_index = 0

if __name__ == '__main__':
    filepath = "imput.pmx"
    read_pmx_data(bpy.context, filepath)
    pass
