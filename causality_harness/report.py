def generate(ces):

    print("\nFINAL CAUSALITY REPORT")
    print("="*40)

    for k, v in ces.items():
        if v < 0.1:
            label = "NO EFFECT"
        elif v < 0.3:
            label = "WEAK COUPLING"
        elif v < 0.6:
            label = "PARTIAL INTEGRATION"
        else:
            label = "STRONG CAUSAL DRIVER"

        print(f"{k}: {v:.3f} → {label}")
