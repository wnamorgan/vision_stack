"""
gimbal_camera_calibration.py

Single-file implementation of a gimbal–camera calibration using
rotation-vector (axis–angle) residuals and nonlinear least squares.

When imported:
    - provides SO(3) utilities
    - provides residual construction
    - provides a solve() entry point
"""

import numpy as np
from scipy.optimize import least_squares

# ============================================================
# SO(3) utilities
# ============================================================

def skew(v):
    x, y, z = v
    return np.array([[0, -z,  y],
                     [z,  0, -x],
                     [-y, x,  0]])

def exp_so3(phi):
    theta = np.linalg.norm(phi)
    if theta < 1e-12:
        return np.eye(3)
    u = phi / theta
    U = skew(u)
    return (
        np.eye(3)
        + np.sin(theta) * U
        + (1 - np.cos(theta)) * (U @ U)
    )

def log_so3(R):
    c = (np.trace(R) - 1) / 2
    c = np.clip(c, -1, 1)
    theta = np.arccos(c)
    if theta < 1e-12:
        return np.zeros(3)
    return (
        theta / (2 * np.sin(theta))
        * np.array([
            R[2,1] - R[1,2],
            R[0,2] - R[2,0],
            R[1,0] - R[0,1],
        ])
    )

# ============================================================
# Gimbal kinematics (example)
# ============================================================

def Rz(a):
    ca, sa = np.cos(a), np.sin(a)
    return np.array([[ ca, -sa, 0],
                     [ sa,  ca, 0],
                     [  0,   0, 1]])

def Ry(a):
    ca, sa = np.cos(a), np.sin(a)
    return np.array([[ ca, 0, sa],
                     [  0, 1,  0],
                     [-sa, 0, ca]])

def Rx(a):
    ca, sa = np.cos(a), np.sin(a)
    return np.array([[1,  0,   0],
                     [0, ca, -sa],
                     [0, sa,  ca]])

def R_m_g(enc, theta0):
    yaw, pitch, roll = enc
    return Rz(yaw) @ Ry(pitch + theta0) @ Rx(roll)

def R_c_m(omega_mc):
    return exp_so3(omega_mc)

# ============================================================
# Data container
# ============================================================

class Maneuver:
    def __init__(self, R_c_meas, enc_start, enc_end):
        self.R_c_meas = R_c_meas
        self.enc_start = np.asarray(enc_start)
        self.enc_end   = np.asarray(enc_end)

# ============================================================
# Residual and solver
# ============================================================

def make_residual(maneuvers):

    def residual(x):
        theta0   = x[0]
        omega_mc = x[1:4]
        Rcm = R_c_m(omega_mc)

        r = []

        for m in maneuvers:
            Rg1 = R_m_g(m.enc_end,   theta0)
            Rg0 = R_m_g(m.enc_start, theta0)
            Delta_R_m = Rg1 @ Rg0.T
            Delta_R_c_pred = Rcm @ Delta_R_m @ Rcm.T
            E = m.R_c_meas.T @ Delta_R_c_pred
            r.append(log_so3(E))

        return np.concatenate(r)

    return residual

def solve_calibration(maneuvers, x0=None):
    if x0 is None:
        x0 = np.zeros(4)
    residual = make_residual(maneuvers)
    return least_squares(residual, x0)
