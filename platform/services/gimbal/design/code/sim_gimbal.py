import numpy as np
import gimbal_camera_calibration as gcal
from gimbal_camera_calibration import (
    R_m_g, R_c_m, Maneuver, solve_calibration
)

# ------------------------------------------------------------
# Ground-truth calibration parameters
# ------------------------------------------------------------

theta0_true = np.deg2rad(127)

ang = np.deg2rad([-130,150,120])
R_m_to_c = gcal.Rx(ang[0]) @ gcal.Ry(ang[1]) @ gcal.Rz(ang[2])
omega_mc_true = gcal.log_so3(R_m_to_c)


#omega_mc_true = np.array([0.03, -0.02, 0.04])

Rcm_true = R_c_m(omega_mc_true)

# ------------------------------------------------------------
# Define two gimbal motion segments
# ------------------------------------------------------------

encoders = [
    np.array([0.0,  0.0, 0.0]),
    np.array([0.4,  0.3, 0.0]),
    np.array([0.8, -0.2, 0.0]),
    np.array([0.0,  0.0, 0.5]),
]

maneuvers = []

for enc_start, enc_end in zip(encoders[:-1], encoders[1:]):

    Rg_start = R_m_g(enc_start, theta0_true)
    Rg_end   = R_m_g(enc_end,   theta0_true)

    Delta_R_m = Rg_end @ Rg_start.T
    Delta_R_c = Rcm_true @ Delta_R_m @ Rcm_true.T

    maneuvers.append(
        Maneuver(
            R_c_meas=Delta_R_c,
            enc_start=enc_start,
            enc_end=enc_end
        )
    )

# ------------------------------------------------------------
# Solve calibration
# ------------------------------------------------------------

sol = solve_calibration(maneuvers)

print("\n=== TRUE PARAMETERS ===")
print("theta0      :", np.rad2deg(theta0_true))
print("omega_mc    :", omega_mc_true)

print("\n=== ESTIMATED PARAMETERS ===")
print("theta0_hat  :", np.rad2deg(sol.x[0]))
print("omega_mc_hat:", sol.x[1:4])

print("\nResidual norm:", np.linalg.norm(sol.fun))
