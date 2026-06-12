import math
from collections import Counter

def cosine(a, b):
    # Word count vectorizer (Term Frequency Cosine Similarity)
    words_a = a.lower().split()
    words_b = b.lower().split()
    
    if not words_a or not words_b:
        # Acknowledge full identical matches defensively
        if a.strip() == b.strip():
            return 1.0
        return 0.0
        
    cnt_a = Counter(words_a)
    cnt_b = Counter(words_b)
    
    intersection = set(cnt_a.keys()) & set(cnt_b.keys())
    numerator = sum(cnt_a[x] * cnt_b[x] for x in intersection)
    
    sum_a = sum(val ** 2 for val in cnt_a.values())
    sum_b = sum(val ** 2 for val in cnt_b.values())
    
    denominator = math.sqrt(sum_a) * math.sqrt(sum_b)
    
    if not denominator:
        return 0.0
    return float(numerator / denominator)

def structural_metrics(text):
    return {
        "length": len(text),
        "has_reflection": "I think" in text or "I believe" in text,
        "has_confidence": "sure" in text.lower(),
        "sentences": text.count(".")
    }
