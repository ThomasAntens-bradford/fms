from enum import Enum, auto

class TVTestParameters(Enum):
    LOGTIME = 'logtime'
    ANODE_FLOW = 'anode_flow_rate'
    GAS_SELECT = 'gas_select'
    FILTERED_OUTLET_TEMP = 'filtered_outlet_temp'
    BODY_TEMP = 'body_temp'
    OUTLET_TEMP = 'outlet_temp'
    FILTERED_BODY_TEMP = 'filtered_body_temp'

class FRParts(Enum):
    FILTER = 'ejay filter'
    OUTLET = 'restrictor outlet'
    RESTRICTOR = 'flow restrictor'
    ANODE = 'anode flow restrictor'
    CATHODE = 'cathode flow restrictor'

class TVParts(Enum):
    MAIN_BODY = 'thermal valve main body'
    PLUNGER = 'thermal valve plunger'
    NUT = 'thermal valve nut'
    SEALING = 'thermal valve sealing element'
    GASKET = 'thermal valve gasket'
    HOLDER_1 = 'thermal valve holder 1'
    HOLDER_2 = 'thermal valve holder 2'
    WELD = 'thermal valve weld only'

class LimitStatus(Enum):
    """
    Enum representing within limits (True), outside limits (False), or on limit (On Limit).
    """
    TRUE = 'true'
    FALSE = 'false'
    ON_LIMIT = 'on_limit'

class FunctionalTestType(Enum):
    HIGH_OPEN_LOOP = 'high_open_loop'
    HIGH_CLOSED_LOOP = 'high_closed_loop'
    LOW_OPEN_LOOP = 'low_open_loop'
    LOW_CLOSED_LOOP = 'low_closed_loop'
    LOW_SLOPE = 'low_slope'
    HIGH_SLOPE = 'high_slope'
    ROOM = 'room_temp'
    HOT = 'hot_temp'
    COLD = 'cold_temp'
    NONE = 'none'

class FMSParts(Enum):
    MANIFOLD = 'manifold'
    TV = 'thermal valve'
    HPIV = 'hpiv'
    
class FMSProgressStatus(Enum):
    AWAITING_PART_AVAILABILITY = 'awaiting_part_availability'
    ASSEMBLY_COMPLETED = 'assembly_completed'
    TESTING_COMPLETED = 'testing_completed'
    TESTING = 'testing'
    TVAC_COMPLETED = 'tvac_completed'
    READY_FOR_TVAC = 'ready_for_tvac'
    DELIVERED = 'delivered'
    SHIPMENT = 'shipment'
    SCRAPPED = 'scrapped'

class FRStatus(Enum):
    DIFF_THICKNESS = 'diff_thickness'
    DIFF_ORIFICE = 'diff_orifice'
    DIFF_FLOWRATE = 'diff_flow_rate'
    DIFF_GEOMETRY = 'diff_geometry'
    DIFF_RADIUS = 'diff_radius'
    OK = 'ok'

class TVProgressStatus(Enum):
    """
    Enum representing the status of a process.
    """
    COMPLETED = 'completed'
    ASSEMBLY_COMPLETED = 'assembly_completed'
    SETTING_TEMPERATURE = 'setting_temperature'
    WELDING_TEST = 'welding_test'
    READY_FOR_WELD = 'ready_for_weld'
    WELDING_COMPLETED = 'welding_completed'
    TESTING_COMPLETED = 'testing_completed'
    COIL_MOUNTED = 'coil_mounted'
    FAILED = 'failed'

class ManifoldProgressStatus(Enum):
    FLOW_TESTING = 'flow_testing'
    AC_RATIO_SET = 'ac_ratio_set'
    WELDING_COMPLETED = 'welding_completed'
    COMPLETED = 'completed'
    AVAILABLE = 'available'
    ASSEMBLY_COMPLETED = 'assembly_completed'

class FMSFlowTestParameters(Enum):
    LOGTIME = 'logtime'
    Tu = 'Tu'
    Ku = 'Ku'
    HEATER_GAIN = 'heater_gain'
    HEATER_INTEGRAL = 'heater_integral'
    CLOSED_LOOP_TEMP = 'closed_loop_temp'
    LPT_VOLTAGE = 'lpt_voltage'
    LPT_PRESSURE = 'lpt_pressure'
    BRIDGE_VOLTAGE = 'bridge_voltage'
    LPT_TEMP = 'lpt_temp'
    DUTY_CYCLE_2 = 'duty_cycle_2'
    DUTY_CYCLE = 'duty_cycle'
    CLOSED_LOOP_PRESSURE = 'closed_loop_pressure'
    INLET_PRESSURE = 'inlet_pressure'
    PC1_PRESSURE = 'pc1_pressure'
    PC1_SETPOINT = 'pc1_setpoint'
    PC3_PRESSURE = 'pc3_pressure'
    PC3_SETPOINT = 'pc3_setpoint'
    ANODE_PRESSURE = 'anode_pressure'
    ANODE_TEMP = 'anode_temp'
    ANODE_FLOW = 'anode_flow'
    CATHODE_PRESSURE = 'cathode_pressure'
    CATHODE_TEMP = 'cathode_temp'
    CATHODE_FLOW = 'cathode_flow'
    ANODE_CATHODE_RATIO = 'anode_cathode_ratio'
    VACUUM_PRESSURE = 'vacuum_pressure'
    TV_PT1000 = 'tv_pt1000'
    ANODE_EST_FLOW = 'anode_est_flow'
    CATHODE_EST_FLOW = 'cathode_est_flow'
    AC_GAS_SELECT = 'ac_gas_select'
    FILTERED_LPT_TEMP = 'filtered_lpt_temp'
    HPIV_STATUS = 'hpiv_status'
    TV_POWER = 'tv_power'
    TV_VOLTAGE = 'tv_voltage'
    TV_CURRENT = 'tv_current'
    TOTAL_FLOW = 'total_flow'
    AVG_TV_POWER = 'avg_tv_power'

class FMSMainParameters(Enum):
    SERIAL_NUMBER = 'serial_number'
    MASS = 'mass'
    POWER_BUDGET_COLD = 'power_budget_cold'
    POWER_BUDGET_ROOM = 'power_budget_room'
    POWER_BUDGET_HOT = 'power_budget_hot'
    HIGH_PROOF_PRESSURE = 'high_proof_pressure'
    LOW_PROOF_PRESSURE = 'low_proof_pressure'
    ROOM_HPIV_DROPOUT_VOLTAGE = 'room_hpiv_dropout_voltage'
    ROOM_HPIV_PULLIN_VOLTAGE = 'room_hpiv_pullin_voltage'
    ROOM_HPIV_CLOSING_RESPONSE = 'room_hpiv_closing_response'
    ROOM_HPIV_HOLD_POWER = 'room_hpiv_hold_power'
    ROOM_HPIV_OPENING_RESPONSE = 'room_hpiv_opening_response'
    ROOM_HPIV_OPENING_POWER = 'room_hpiv_opening_power'
    ROOM_HPIV_INDUCTANCE = 'room_hpiv_inductance'
    ROOM_TV_INDUCTANCE = 'room_tv_inductance'
    ROOM_HPIV_RESISTANCE = 'room_hpiv_resistance'
    ROOM_TV_PT_RESISTANCE = 'room_tv_pt_resistance'
    ROOM_TV_RESISTANCE = 'room_tv_resistance'
    ROOM_LPT_RESISTANCE = 'room_lpt_resistance'
    ROOM_TV_HIGH_LEAK = 'room_tv_high_leak'
    ROOM_TV_LOW_LEAK = 'room_tv_low_leak'
    ROOM_TV_LOW_LEAK_OPEN = 'room_tv_low_leak_open'
    ROOM_HPIV_HIGH_LEAK = 'room_hpiv_high_leak'
    ROOM_HPIV_LOW_LEAK = 'room_hpiv_low_leak'
    COLD_HPIV_DROPOUT_VOLTAGE = 'cold_hpiv_dropout_voltage'
    COLD_HPIV_PULLIN_VOLTAGE = 'cold_hpiv_pullin_voltage'
    COLD_HPIV_CLOSING_RESPONSE = 'cold_hpiv_closing_response'
    COLD_HPIV_HOLD_POWER = 'cold_hpiv_hold_power'
    COLD_HPIV_OPENING_RESPONSE = 'cold_hpiv_opening_response'
    COLD_HPIV_OPENING_POWER = 'cold_hpiv_opening_power'
    COLD_HPIV_INDUCTANCE = 'cold_hpiv_inductance'
    COLD_TV_INDUCTANCE = 'cold_tv_inductance'
    COLD_HPIV_RESISTANCE = 'cold_hpiv_resistance'
    COLD_TV_PT_RESISTANCE = 'cold_tv_pt_resistance'
    COLD_TV_RESISTANCE = 'cold_tv_resistance'
    COLD_LPT_RESISTANCE = 'cold_lpt_resistance'
    COLD_TV_HIGH_LEAK = 'cold_tv_high_leak'
    COLD_TV_LOW_LEAK = 'cold_tv_low_leak'
    COLD_TV_LOW_LEAK_OPEN = 'cold_tv_low_leak_open'
    COLD_HPIV_HIGH_LEAK = 'cold_hpiv_high_leak'
    COLD_HPIV_LOW_LEAK = 'cold_hpiv_low_leak'
    HOT_HPIV_DROPOUT_VOLTAGE = 'hot_hpiv_dropout_voltage'
    HOT_HPIV_PULLIN_VOLTAGE = 'hot_hpiv_pullin_voltage'
    HOT_HPIV_CLOSING_RESPONSE = 'hot_hpiv_closing_response'
    HOT_HPIV_HOLD_POWER = 'hot_hpiv_hold_power'
    HOT_HPIV_OPENING_RESPONSE = 'hot_hpiv_opening_response'
    HOT_HPIV_OPENING_POWER = 'hot_hpiv_opening_power'
    HOT_HPIV_INDUCTANCE = 'hot_hpiv_inductance'
    HOT_TV_INDUCTANCE = 'hot_tv_inductance'
    HOT_HPIV_RESISTANCE = 'hot_hpiv_resistance'
    HOT_TV_PT_RESISTANCE = 'hot_tv_pt_resistance'
    HOT_TV_RESISTANCE = 'hot_tv_resistance'
    HOT_LPT_RESISTANCE = 'hot_lpt_resistance'
    HOT_TV_HIGH_LEAK = 'hot_tv_high_leak'
    HOT_TV_LOW_LEAK = 'hot_tv_low_leak'
    HOT_TV_LOW_LEAK_OPEN = 'hot_tv_low_leak_open'
    HOT_HPIV_HIGH_LEAK = 'hot_hpiv_high_leak'
    HOT_HPIV_LOW_LEAK = 'hot_hpiv_low_leak'
    TV_HIGH_LEAK = 'tv_high_leak'
    TV_LOW_LEAK = 'tv_low_leak'
    HPIV_HIGH_LEAK = 'hpiv_high_leak'
    HPIV_LOW_LEAK = 'hpiv_low_leak'
    INLET_LOCATION = 'inlet_location'
    OUTLET_ANODE = 'outlet_anode'
    OUTLET_CATHODE = 'outlet_cathode'
    FMS_ENVELOPE = 'fms_envelope'
    TV_HOUSING_BONDING = 'tv_housing_bonding'
    BONDING_TV_HOUSING = 'bonding_tv_housing'
    TV_HOUSING_HPIV = 'tv_housing_hpiv'
    HPIV_HOUSING_TV = 'hpiv_housing_tv'
    LPT_HOUSING_BONDING = 'lpt_housing_bonding'
    BONDING_LPT_HOUSING = 'bonding_lpt_housing'
    J01_BONDING = 'j01_bonding'
    BONDING_J01 = 'bonding_j01'
    J02_BONDING = 'j02_bonding'
    BONDING_J02 = 'bonding_j02'
    J01_PIN_BONDING = 'j01_pin_bonding'
    BONDING_J01_PIN = 'bonding_j01_pin'
    J02_PIN_BONDING = 'j02_pin_bonding'
    BONDING_J02_PIN = 'bonding_j02_pin'
    LPT_PSIG = 'lpt_psig'
    LPT_PSIGRTN = 'lpt_psig_rtn'
    ISO_LPT_TSIG = 'iso_lpt_tsig'
    ISO_LPT_TSIGRTN = 'iso_lpt_tsig_rtn'
    LPT_PWR = 'lpt_power'
    LPT_PWRRTN = 'lpt_power_rtn'
    ISO_PT_SGN = 'iso_pt_sgn'
    ISO_PT_SGNRTN = 'iso_pt_sgn_rtn'
    TV_PWR = 'tv_power'
    TV_PWRRTN = 'tv_power_rtn'
    HPIV_PWR = 'hpiv_power'
    HPIV_PWRRTN = 'hpiv_power_rtn'
    CAP_LPT_TSIG = 'cap_lpt_tsig'
    CAP_LPT_TSIGRTN = 'cap_lpt_tsig_rtn'
    CAP_PT_SGN = 'cap_pt_sgn'
    CAP_PT_SGNRTN = 'cap_pt_sgn_rtn'
    LPT_RESISTANCE = 'lpt_resistance'
    TV_RESISTANCE = 'tv_resistance'
    TV_PT_RESISTANCE = 'tv_pt_resistance'
    HPIV_RESISTANCE = 'hpiv_resistance'
    HPIV_OPENING_POWER = 'hpiv_opening_power'
    HPIV_OPENING_RESPONSE = 'hpiv_opening_response'
    HPIV_HOLD_POWER = 'hpiv_hold_power'
    HPIV_CLOSING_RESPONSE = 'hpiv_closing_response'
    HPIV_PULLIN_VOLTAGE = 'hpiv_pullin_voltage'
    HPIV_DROPOUT_VOLTAGE = 'hpiv_dropout_voltage'
    LOW_PRESSURE_EXT_LEAK = 'low_pressure_ext_leak'
    HIGH_PRESSURE_EXT_LEAK_LOW = 'high_pressure_ext_leak_low'
    HIGH_PRESSURE_EXT_LEAK_HIGH = 'high_pressure_ext_leak_high'

class FMSTvacParameters(Enum):
    TIME = 'logtime'
    TRP1 = 'trp1'
    TRP2 = 'trp2'
    TV_INLET_TEMP = 'tv_inlet'
    MANIFOLD_TEMP = 'manifold'
    LPT_TEMP = 'lpt'
    HPIV_TEMP = 'hpiv'
    TV_OUTLET_TEMP = 'tv_outlet'
    FMS_INLET_TEMP = 'fms_inlet'
    ANODE_OUTLET_TEMP = 'anode'
    CATHODE_OUTLET_TEMP = 'cathode'

class TVTvacParameters(Enum):
    SCAN = "scan"
    TIME = "time"
    OUTLET_TEMP_1 = "outlet_temp_1"
    ALARM_101 = "alarm_101"
    OUTLET_TEMP_2 = "outlet_temp_2"
    ALARM_102 = "alarm_102"
    INTERFACE_TEMP = "interface_temp"
    ALARM_103 = "alarm_103"
    IF_PLATE = "if_plate"
    ALARM_104 = "alarm_104"
    VACUUM = "vacuum"
    ALARM_109 = "alarm_109"
    TV_VOLTAGE = "tv_voltage"
    ALARM_110 = "alarm_110"
    TV_CURRENT = "tv_current"
    ALARM_121 = "alarm_121"

class TVTvacParameters2(Enum):
    SCAN = "scan"
    TIME = "time"
    OUTLET_ELBOW = "outlet_elbow"
    ALARM_101 = "alarm_101"
    OUTLET_TEMP_1 = "outlet_temp_1"
    ALARM_102 = "alarm_102"
    INTERFACE_TEMP = "interface_temp"
    ALARM_103 = "alarm_103"
    OUTLET_TEMP_2 = "outlet_temp_2"
    ALARM_104 = "alarm_104"
    IF_PLATE_1 = "if_plate_1"
    ALARM_105 = "alarm_105"
    IF_PLATE_2 = "if_plate_2"
    ALARM_106 = "alarm_106"
    VACUUM = "vacuum"
    ALARM_109 = "alarm_109"
    TV_VOLTAGE = "tv_voltage"
    ALARM_110 = "alarm_110"
    TV_CURRENT = "tv_current"
    ALARM_121 = "alarm_121"

class HPIVParameters(Enum):
    """
    Enum defining all HPIV (High Pressure Isolation Valve) test parameters.
    
    This enumeration contains all the parameters that can be measured or tested
    during HPIV acceptance testing, including pressure tests, electrical tests,
    vibration tests, and cleanliness measurements.
    """
    HPIV_ID = "serial_nr"
    WEIGHT = "weight"
    PROOF_CLOSED = "proof_closed"
    PROOF_OPEN = "proof_open"
    LEAK_4_HP = "leak_4_hp"
    LEAK_4_LP = "leak_4_lp"
    LEAK_6_HP = "leak_6_hp"
    LEAK_6_LP = "leak_6_lp"
    LEAK_15_HP = "leak_15_hp"
    LEAK_15_LP = "leak_15_lp"
    LEAK_4_HP_PRESS = "leak_4_hp_press"
    LEAK_4_LP_PRESS = "leak_4_lp_press"
    LEAK_6_HP_PRESS = "leak_6_hp_press"
    LEAK_6_LP_PRESS = "leak_6_lp_press"
    LEAK_15_HP_PRESS = "leak_15_hp_press"
    LEAK_15_LP_PRESS = "leak_15_lp_press"
    DIELECTRIC_STR = "dielectric_str"
    INSULATION_RES = "insulation_res"
    POWER_TEMP = "power_temp"
    POWER_RES = "power_res"
    POWER_POWER = "power_power"
    EXT_LEAK = "ext_leak"
    PULLIN_PRES = "pullin_pres"
    PULLIN_VOLT = "pullin_volt"
    DROPOUT_VOLT = "dropout_volt"
    RESPO_PRES = "resp_pres"
    RESPO_VOLT = "respo_volt"
    RESPO_TIME = "respo_time"
    RESPC_VOLT = "respc_volt"
    RESPC_TIME = "respc_time"
    FLOWRATE = "flowrate"
    PRESSD = "pressd"
    CLEANLINESS_6_10 = "cleanliness_6_10"
    CLEANLINESS_11_25 = "cleanliness_11_25"
    CLEANLINESS_26_50 = "cleanliness_26_50"
    CLEANLINESS_51_100 = "cleanliness_51_100"
    CLEANLINESS_100 = "cleanliness_100"
    BEFORE_VIB_PEAK_X = "before_vib_peak_x"
    BEFORE_VIB_FREQ_X = "before_vib_freq_x"
    BEFORE_VIB_PEAK_Y = "before_vib_peak_y"
    BEFORE_VIB_FREQ_Y = "before_vib_freq_y"
    AFTER_VIB_PEAK_X = "after_vib_peak_x"
    AFTER_VIB_FREQ_X = "after_vib_freq_x"
    AFTER_VIB_PEAK_Y = "after_vib_peak_y"
    AFTER_VIB_FREQ_Y = "after_vib_freq_y"
    VIB_GRMS_X = "vib_grms_x"
    VIB_GRMS_Y = "vib_grms_y"

class HPIVParts(Enum):
    HPIV = "hpiv"
    SEAT_BODY = "seat body"
    COIL_ASSY = "coil assy"
    SPOOL_ASSY = "spool assy"
    SPOOL_ASSY_R = "spool assy_r"
    LOWER_SPOOL = "lower spool"
    NON_MAGNETIC_TUBE = "non magnetic tube"
    UPPER_SPOOL = "upper spool"
    COPPER_WIRE = "copper wire"
    KAPTON_TAPE = "kapton tape"
    LEAD_WIRE = "lead wire"
    SHRINK_TUBE = "shrink tube"
    SOLDER_FILLER = "solder filler"
    HOUSING = "housing"
    PLUNGER_ASSY = "plunger assy"
    PLUNGER_R = "plunger_r"
    SEAL = "seal"
    DISK_SPRING = "disk spring"
    SPRING = "spring"
    SHIM1 = "shim1"
    SHIM2 = "shim2"
    FILTER_ASSY = "filter assy"
    FRAME = "frame"
    SUPPORTER = "supporter"
    MESH = "mesh"

class LPTCoefficientParameters(Enum):
    LPT_ID = 'lpt_id'
    A0_P = 'a0_p'
    A1_P = 'a1_p'
    A2_P = 'a2_p'
    A3_P = 'a3_p'
    B0_P = 'b0_p'
    B1_P = 'b1_p'
    B2_P = 'b2_p'
    B3_P = 'b3_p'
    C0_P = 'c0_p'
    C1_P = 'c1_p'
    C2_P = 'c2_p'
    C3_P = 'c3_p'
    D0_P = 'd0_p'
    D1_P = 'd1_p'
    D2_P = 'd2_p'
    D3_P = 'd3_p'
    A0_T = 'a0_t'
    A1_T = 'a1_t'
    A2_T = 'a2_t'
    A3_T = 'a3_t'
    B0_T = 'b0_t'
    B1_T = 'b1_t'
    B2_T = 'b2_t'
    B3_T = 'b3_t'
    C0_T = 'c0_t'
    C1_T = 'c1_t'
    C2_T = 'c2_t'
    C3_T = 'c3_t'
    D0_T = 'd0_t'
    D1_T = 'd1_t'
    D2_T = 'd2_t'
    D3_T = 'd3_t'