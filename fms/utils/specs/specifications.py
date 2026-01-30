fms_specifications = {
    "lpt_pressures": [0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.4],
    "lpt_voltages": [10, 15, 17, 20, 24, 25, 30, 35],
    "min_flow_rates": [0.61, 1.23, 1.51, 1.85, 2.40, 2.43, 3.13, 3.72],
    "max_flow_rates": [0.96, 1.61, 1.9, 2.34, 2.93, 3.07, 3.81, 4.54],
    "range12_low": [13, 41],
    "range24_low": [19, 54],
    "range12_high": [25, 95],
    "range24_high": [35, 140],
    "initial_flow_rate": 0.035,
    "lpt_set_points": [1, 1.625, 2.25, 1.625, 1, 0.2],
    "max_opening_response": 300, 
    "max_response": 60
}

fr_specifications = {
        "anode_reference_orifice": 0.07095,
        "cathode_reference_orifice": 0.01968, 
        "reference_thickness": 0.25, 
        "thickness_tolerance": 0.01
}

manifold_specifications = {
    "min_radius": 0.22, 
    "max_radius": 0.25, 
    "ref_thickness": 0.25, 
    "thickness_tol": 0.01, 
    "anode_reference_orifice": 0.07095, 
    "cathode_reference_orifice": 0.01968,
    "anode_target_15": 3.006, 
    "anode_target_24": 4.809, 
    "cathode_target_15": 0.231, 
    "cathode_target_24": 0.370, 
    "pressure_threshold": 0.2, 
    "signal_tolerance": 0.05, 
    "signal_threshold": 7.5, 
    "anode_fs": 20, 
    "cathode_fs": 2,
    "fs_error": 0.001, 
    "reading_error": 0.005, 
    "xenon_density": 5.894, 
    "krypton_density": 3.749
}