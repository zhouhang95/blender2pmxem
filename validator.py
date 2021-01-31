#
# validator.py
#
# These codes are licensed under CC0.
# http://creativecommons.org/publicdomain/zero/1.0/deed.ja
#

from .pmx import pmx
from typing import List

def check_unique(name_list: List[str], category: str) -> List[str]:
    result = []
    name_set = set()
    for i in range(len(name_list)):
        name = name_list[i]
        if name not in name_set:
            name_set.add(name)
        else:
            result.append('{} name {}:{} must be unique in PMX.'.format(category, i, name))
    return result

def validate_pmx(pmx_data: pmx.Model, use_ja_name: bool) -> List[str]:
    result = []

    if use_ja_name:
        morph_name_list = [morph.Name for morph in pmx_data.Morphs]
        result.extend(check_unique(morph_name_list, 'Morph Japanese'))

        bone_name_list = [bone.Name for bone in pmx_data.Bones]
        result.extend(check_unique(bone_name_list, 'Bone Japanese'))
    else:
        morph_name_list = [morph.Name_E for morph in pmx_data.Morphs]
        result.extend(check_unique(morph_name_list, 'Morph English'))

        bone_name_list = [bone.Name_E for bone in pmx_data.Bones]
        result.extend(check_unique(bone_name_list, 'Bone English')) 


    rigid_name_list = [rigid.Name for rigid in pmx_data.Rigids]
    result.extend(check_unique(rigid_name_list, 'Rigid English')) 

    joint_name_list = [joint.Name for joint in pmx_data.Joints]
    result.extend(check_unique(joint_name_list, 'Joint English')) 

    return result

