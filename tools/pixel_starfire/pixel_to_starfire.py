#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pixel_to_starfire.py — 像素坐标到星火坐标的数学转换核心。

公开函数：
    pixel_to_mm(px, py, params, poly_config) -> (x_mm, y_mm)
        使用多项式拟合参数将像素坐标转换为毫米坐标。
    mm_to_starfire(x_mm, y_mm) -> (sx, sy)
        毫米坐标乘以 1000/25.4 换算为星火单位。

配置文件位置：config/device/{device}/{camera_position}/
    fit_params.json       — 多项式系数
    polynomials_fit.json  — 多项式结构定义
"""
import logging
logger = logging.getLogger(__name__)

import json
from pathlib import Path

ROOT = Path(__file__).parent
DEVICE_DIR = ROOT / "config" / "device" / "M7"


def load_params(camera_position: int):
    cam_dir = DEVICE_DIR / str(camera_position)
    with open(cam_dir / "fit_params.json", encoding="utf-8") as f:
        params = json.load(f)
    with open(cam_dir / "polynomials_fit.json", encoding="utf-8") as f:
        poly_config = json.load(f)
    return params, poly_config


def evaluate_term(term: dict, x: float, y: float) -> float:
    factors = term.get("factors", [])
    if not factors:
        return 1.0
    value = 1.0
    for factor in factors:
        var = factor["var"]
        power = factor.get("pow", 1)
        shift = factor.get("shift", 0.0)
        base = (x if var == "x" else y) - shift
        value *= base ** power
    return value


def pixel_to_mm(px: float, py: float, params: dict, poly_config: dict):
    polys = poly_config["polynomials"]
    result = {}
    for poly in polys:
        name = poly["name"]
        coefs = params[name]
        total = 0.0
        for term in poly["terms"]:
            coef = float(coefs[term["coef"]])
            total += coef * evaluate_term(term, px, py)
        result[name] = total
    return result["x_new"], result["y_new"]


def mm_to_starfire(x_mm: float, y_mm: float):
    factor = 1000.0 / 25.4
    return x_mm * factor, y_mm * factor
