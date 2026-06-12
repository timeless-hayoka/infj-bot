CONDITIONS = {
    "A_BASELINE": {
        "pedi": "real",
        "dii": "real",
        "homeostasis": "real"
    },

    "B_NO_PEDI": {
        "pedi": None,
        "dii": "real",
        "homeostasis": "real"
    },

    "C_SHUFFLED_DII": {
        "pedi": "real",
        "dii": "randomized",
        "homeostasis": "real"
    },

    "D_FROZEN_HOMEOSTASIS": {
        "pedi": "real",
        "dii": "real",
        "homeostasis": "static"
    },

    "E_ALL_FROZEN": {
        "pedi": "static",
        "dii": "static",
        "homeostasis": "static"
    }
}
