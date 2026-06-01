"""
inverse_transform.py — 多项式逆变换算法。
从 vgs/algorithms/utils.py 提取，仅保留 apply_inverse_transform 所需的函数。
"""
import json
from typing import Dict, List, Tuple, Any

import numpy as np


def load_polynomial_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_params_config(filename: str) -> Dict:
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)


def evaluate_term_value(term: Dict[str, Any], variables: Dict[str, float]) -> float:
    factors = term.get('factors', [])
    if not factors:
        return 1.0
    value = 1.0
    for factor in factors:
        var_name = factor['var']
        power = factor.get('pow', 1)
        shift = factor.get('shift', 0.0)
        base = float(variables[var_name]) - float(shift)
        value *= base ** power
    return value


def evaluate_polynomial_value(polynomial: Dict[str, Any], variables: Dict[str, float], coef_values: Dict[str, float]) -> float:
    total = 0.0
    for term in polynomial.get('terms', []):
        coef_name = term['coef']
        coef = float(coef_values[coef_name])
        total += coef * evaluate_term_value(term, variables)
    return total


def evaluate_polynomials(polynomials: List[Dict[str, Any]], variables: Dict[str, float], coef_values_by_poly: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    out = {}
    for poly in polynomials:
        name = poly['name']
        out[name] = evaluate_polynomial_value(poly, variables, coef_values_by_poly[name])
    return out


def evaluate_jacobian_xy(polynomials: List[Dict[str, Any]], variables: Dict[str, float], coef_values_by_poly: Dict[str, Dict[str, float]]) -> np.ndarray:
    J = np.zeros((2, 2), dtype=float)

    for row_idx, poly in enumerate(polynomials[:2]):
        for col_idx, wrt in enumerate(['x', 'y']):
            deriv_sum = 0.0
            for term in poly.get('terms', []):
                coef = float(coef_values_by_poly[poly['name']][term['coef']])
                factors = term.get('factors', [])
                if not factors:
                    continue
                term_contrib = 0.0
                for k, factor_k in enumerate(factors):
                    var_name = factor_k['var']
                    power = factor_k.get('pow', 1)
                    shift = factor_k.get('shift', 0.0)
                    if var_name != wrt:
                        continue
                    base = float(variables[var_name]) - float(shift)
                    if power == 0:
                        d_factor = 0.0
                    elif power == 1:
                        d_factor = 1.0
                    else:
                        d_factor = power * (base ** (power - 1))
                    prod_other = 1.0
                    for j, factor_j in enumerate(factors):
                        if j == k:
                            continue
                        var_j = factor_j['var']
                        pow_j = factor_j.get('pow', 1)
                        shift_j = factor_j.get('shift', 0.0)
                        base_j = float(variables[var_j]) - float(shift_j)
                        prod_other *= base_j ** pow_j
                    term_contrib += d_factor * prod_other
                deriv_sum += coef * term_contrib
            J[row_idx, col_idx] = deriv_sum
    return J


def newton_inverse(polynomials, coef_values_by_poly, target_xy, initial_guess=None, max_iters: int = 20, tol: float = 1e-7):
    if initial_guess is None:
        x0, y0 = target_xy
    else:
        x0, y0 = initial_guess
    current = np.array([float(x0), float(y0)], dtype=float)
    target = np.array([float(target_xy[0]), float(target_xy[1])], dtype=float)

    for it in range(max_iters):
        variables = {'x': current[0], 'y': current[1]}
        values = evaluate_polynomials(polynomials[:2], variables, coef_values_by_poly)
        F = np.array([values[polynomials[0]['name']], values[polynomials[1]['name']]], dtype=float)
        resid = F - target
        if np.linalg.norm(resid, ord=2) < tol:
            return current, True, it
        J = evaluate_jacobian_xy(polynomials, variables, coef_values_by_poly)
        try:
            delta = np.linalg.solve(J, resid)
        except np.linalg.LinAlgError:
            delta = np.linalg.pinv(J).dot(resid)
        current = current - delta
    return current, False, max_iters


def inverse_transform_points(points_B, config, coef_values_by_poly, initial_guess=None, max_iters: int = 20, tol: float = 1e-7):
    polynomials = config['polynomials']
    results = []
    for x_new, y_new in points_B:
        guess = tuple(initial_guess) if initial_guess is not None else (x_new, y_new)
        sol, ok, iters = newton_inverse(polynomials, coef_values_by_poly, (float(x_new), float(y_new)), guess, max_iters, tol)
        results.append(sol)
    return np.asarray(results)


def apply_inverse_transform(points, polynomial_path: str, params_path: str):
    """对 PLT 轮廓坐标执行多项式逆变换（物理坐标 → 像素坐标）。"""
    config = load_polynomial_config(polynomial_path)
    coef_values = load_params_config(params_path)

    if isinstance(points, list):
        result_contours = []
        for contour in points:
            contour = np.array(contour)
            if contour.ndim == 3:
                contour = contour.reshape(-1, 2)
            if contour.size == 0:
                result_contours.append(contour)
                continue
            contour = contour * 25.4 / 1000
            new_contour = inverse_transform_points(contour, config, coef_values)
            result_contours.append(new_contour)
        return result_contours
    else:
        points = np.array(points)
        if points.ndim == 3:
            points = points.reshape(-1, 2)
        points = points * 25.4 / 1000
        return inverse_transform_points(points, config, coef_values)
