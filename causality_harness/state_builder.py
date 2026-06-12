import random

def build_state(condition, pedi, dii, homeostasis):

    state = {
        "PEDI_VECTOR": pedi,
        "DII_SCORE": dii,
        "HOMEOSTASIS": homeostasis
    }

    if condition["pedi"] is None:
        state["PEDI_VECTOR"] = [0] * 7

    if condition["dii"] == "randomized":
        state["DII_SCORE"] = random.random()

    if condition["homeostasis"] == "static":
        state["HOMEOSTASIS"] = {
            "needs": 0.5,
            "crisis": 0,
            "regulation": 0
        }

    return state
