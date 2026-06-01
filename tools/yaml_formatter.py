import logging
logger = logging.getLogger(__name__)

"""
YAML格式化工具
格式化YAML文件，使得：
- 两维坐标放在一行（如 `- [x, y]`）
- 坐标数组按行排列，每个坐标一行
"""
import yaml
import os
from typing import Any, Dict
from pathlib import Path


def is_2d_coordinate(item):
    return (
        isinstance(item, list) and
        len(item) == 2 and
        all(isinstance(x, (int, float)) for x in item)
    )


def is_number_array(data):
    if not isinstance(data, list) or len(data) == 0:
        return False
    return all(isinstance(item, (int, float)) for item in data)


def is_coordinate_array(sequence):
    return is_number_array(sequence)


class CustomDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(CustomDumper, self).increase_indent(flow, False)

    def represent_list(self, data):
        if is_2d_coordinate(data):
            return self.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)

        if is_number_array(data) and len(data) < 6:
            return self.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)

        return super(CustomDumper, self).represent_list(data)

    def represent_sequence(self, tag, sequence, flow_style=None):
        if flow_style is False and is_coordinate_array(sequence):
            node = yaml.SequenceNode(tag, [])
            node.flow_style = False
            for item in sequence:
                if is_2d_coordinate(item):
                    item_node = self.represent_data(item)
                    item_node.flow_style = True
                    node.value.append(item_node)
                else:
                    node.value.append(self.represent_data(item))
            return node
        else:
            return super().represent_sequence(tag, sequence, flow_style)


CustomDumper.add_representer(list, CustomDumper.represent_list)


def format_yaml_dict(data: Dict[str, Any], output_path: str):
    """将字典格式化为YAML文件并保存"""
    try:
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(
                data,
                f,
                Dumper=CustomDumper,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=1000,
            )

        return True

    except Exception as e:
        print(f"错误: 处理文件时出错: {e}")
        return False


def format_yaml_file(input_path: str, output_path: str = None, silent: bool = False):
    if not os.path.exists(input_path):
        if not silent:
            print(f"错误: 文件不存在: {input_path}")
        return False

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if data is None:
            if not silent:
                print(f"警告: 文件为空或格式不正确: {input_path}")
            return False

        if output_path is None:
            output_path = input_path

        try:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    data,
                    f,
                    Dumper=CustomDumper,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                    width=1000,
                )

            if not silent:
                print(f"成功格式化YAML文件: {input_path}")
            return True

        except Exception as e:
            if not silent:
                print(f"错误: 处理文件时出错: {e}")
            return False

    except yaml.YAMLError as e:
        if not silent:
            print(f"错误: YAML格式错误: {e}")
        return False
    except Exception as e:
        if not silent:
            print(f"错误: 处理文件时出错: {e}")
        return False
