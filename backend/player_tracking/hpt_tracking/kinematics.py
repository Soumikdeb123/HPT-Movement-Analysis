"""Compatibility API for the shared, experimental metric motion pipeline."""
from .metric_motion import (
    analyse_metric_motion, assess, valid_mass,
    MAX_SPEED as MAXIMUM_PLAYER_SPEED_MPS,
    MAX_ACCELERATION as MAXIMUM_ACCELERATION_MPS2,
)

MINIMUM_CALIBRATION_CONFIDENCE = 0.70
MAXIMUM_GAP_FRAMES = 5  # Legacy only: metric motion uses 0.2 seconds.
MINIMUM_MASS_KG = 20.0
MAXIMUM_MASS_KG = 250.0


def validate_athlete_mass(mass_kg):
    return valid_mass(mass_kg)


def assess_metric_trajectory(samples, fps, calibration_confidence):
    return assess(list(samples), fps, calibration_confidence)


def analyse_force_velocity(samples, fps, athlete_mass_kg, calibration_confidence):
    return analyse_metric_motion(samples, fps, athlete_mass_kg, calibration_confidence)["forceVelocity"]
