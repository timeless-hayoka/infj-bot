import math
import time

def score_memory(mem):
    age = time.time() - mem["timestamp"]
    decay = math.exp(-age / mem.get("tau", 1000))

    reinforcement = mem.get("reinforcement", 1.0)
    salience = mem.get("salience", 1.0)

    confidence = mem.get("confidence", 0.5)

    return decay * reinforcement * salience * confidence
