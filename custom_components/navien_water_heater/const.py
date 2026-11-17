"""Constants for Navien Water Heater integration."""

DOMAIN = "navien_water_heater"

# Source: Navien NPE Service Manual, section 5.1 "Error Code List" (v2.21)
ERROR_CODE_DESCRIPTIONS = {
    3: {0: "Ignition failure"},
    4: {0: "False flame detection"},
    12: {0: "Flame loss"},
    16: {0: "Overheating of heat exchanger"},
    30: {0: "Exhaust overheat: flue temperature exceeded 230°F (110°C) for more than 10 seconds"},
    47: {1: "Abnormal exhaust thermistor (open)", 2: "Abnormal exhaust thermistor (short)"},
    60: {
        1: "Abnormal Dual Venturi limit switch operation (ON)",
        2: "Abnormal Dual Venturi limit switch operation (Close OFF)",
        3: "Abnormal Dual Venturi limit switch operation (Open ON)",
    },
    109: {0: "Abnormal fan motor activity"},
    110: {
        1: "Exhaust blockage (checking the fan)",
        2: "Exhaust blockage (using hot water)",
        3: "Exhaust blockage (using space heating)",
    },
    407: {1: "Abnormal hot water outlet thermistor (open)", 2: "Abnormal hot water outlet thermistor (short)"},
    421: {1: "Abnormal cold water inlet thermistor (open)", 2: "Abnormal cold water inlet thermistor (short)"},
    432: {1: "Abnormal cold water inlet 2 thermistor (open)", 2: "Abnormal cold water inlet 2 thermistor (short)"},
    434: {1: "Abnormal water adjustment valve (open)", 2: "Abnormal water adjustment valve (close)"},
    438: {0: 'Abnormal circulation pump ("A" models only)'},
    439: {0: "Abnormal flow sensor"},
    441: {1: "Abnormal hot water inlet 2 thermistor (open)", 2: "Abnormal hot water inlet 2 thermistor (short)"},
    445: {1: "Abnormal mixing valve (open)", 2: "Abnormal mixing valve (close)"},
    515: {
        **{i: "Abnormal communication between PCB and igniter" for i in range(1, 9)},
        9: "Abnormal communication between PCB and fan",
        10: "Abnormal monitoring device of PCB",
        **{i: "Abnormal communication between PCB and Dual Venturi" for i in (11, 12)},
    },
    517: {0: "Abnormal dip switch setting"},
    593: {1: "Abnormal panel key"},
    594: {
        0: "Abnormal input data from high limit switch of heat exchanger",
        1: "Abnormal input data from exhaust sensor",
        2: "Abnormal input data from flame rod",
        **{i: "Abnormal memory of PCB" for i in range(3, 15)},
        15: "Below the range of input data from pressure sensor",
        16: "Over the range of input data from pressure sensor",
    },
    615: {
        0: "Abnormal input data from high limit switch of heat exchanger",
        1: "Abnormal input data from exhaust sensor",
        2: "Abnormal input data from flame rod",
        **{i: "Abnormal memory of PCB" for i in range(3, 15)},
        15: "Below the range of input data from pressure sensor",
        16: "Over the range of input data from pressure sensor",
    },
    736: {0: "Abnormal cascade communication"},
    740: {
        1: "Abnormal outdoor temperature sensor (open, outdoor reset curve enabled)",
        2: "Abnormal outdoor temperature sensor (short, outdoor reset curve enabled)",
    },
    760: {0: "Flushing/service alarm"},
    782: {0: "Abnormal Main-Panel communication"},
    785: {0: "Abnormal flow switch operation"},
}


def get_error_description(error_code, sub_error_code):
    """Look up the human-readable description for an error/sub-error code pair."""
    return ERROR_CODE_DESCRIPTIONS.get(error_code, {}).get(sub_error_code)
