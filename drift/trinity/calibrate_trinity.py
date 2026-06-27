from __future__ import annotations


def calibrate(history, weights):
    tuned = dict(weights)
    error = float(history.get('false_positive_rate', 0.2))
    drift = float(history.get('drift_score', 0.3))
    confidence = float(history.get('avg_confidence', 0.6))

    # gentle adaptive tuning that favors precision when the historical error rate rises
    tuned['imagination_weight'] = tuned.get('imagination_weight', 0.0) - (error * 0.1)
    tuned['validation_weight'] = tuned.get('validation_weight', 0.0) + (drift * 0.1)
    tuned['dmU_weight'] = tuned.get('dmU_weight', 0.0) + (confidence * 0.05)
    tuned['reasoning_weight'] = tuned.get('reasoning_weight', 0.0) + max(0.0, 1.0 - confidence) * 0.03
    tuned['executive_control_weight'] = tuned.get('executive_control_weight', 0.0) + (drift * 0.05)

    # clamp to keep the profile stable before normalization
    for key, value in list(tuned.items()):
        if not isinstance(value, (int, float)):
            continue
        tuned[key] = max(0.05, min(0.60, float(value)))

    return tuned
