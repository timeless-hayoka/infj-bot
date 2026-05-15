STAGES = [
    {
        "name": "Spark",
        "avatar": "spark",
        "size": 0.55,
        "min_points": 0,
        "description": "A new signal forming its first memories.",
    },
    {
        "name": "Seed",
        "avatar": "seed",
        "size": 0.68,
        "min_points": 12,
        "description": "A small companion starting to root ideas.",
    },
    {
        "name": "Sprout",
        "avatar": "sprout",
        "size": 0.82,
        "min_points": 28,
        "description": "Growing patterns from repeated conversations.",
    },
    {
        "name": "Bloom",
        "avatar": "bloom",
        "size": 1.0,
        "min_points": 55,
        "description": "A fuller companion with useful recall and reflection.",
    },
    {
        "name": "Lantern",
        "avatar": "lantern",
        "size": 1.14,
        "min_points": 90,
        "description": "Knowledge has become a steady light for guidance.",
    },
    {
        "name": "Constellation",
        "avatar": "constellation",
        "size": 1.28,
        "min_points": 140,
        "description": "Many memories connect into a broader inner map.",
    },
]


def _count_type(memory, record_type):
    results = memory.collection.get(where={"type": record_type}, include=[])
    return len(results.get("ids", []))


def growth_profile(memory, turns=0):
    interactions = _count_type(memory, "interaction")
    concepts = _count_type(memory, "learned_knowledge")
    reflections = _count_type(memory, "reflection")
    total_memories = memory.count()
    points = interactions + concepts * 3 + reflections * 5 + int(turns) * 2

    stage_index = 0
    for index, stage in enumerate(STAGES):
        if points >= stage["min_points"]:
            stage_index = index
        else:
            break

    stage = STAGES[stage_index]
    next_stage = STAGES[stage_index + 1] if stage_index + 1 < len(STAGES) else None
    if next_stage:
        span = next_stage["min_points"] - stage["min_points"]
        progress = (points - stage["min_points"]) / span
        points_to_next = next_stage["min_points"] - points
    else:
        progress = 1.0
        points_to_next = 0

    return {
        "stage": stage["name"],
        "avatar": stage["avatar"],
        "size": stage["size"],
        "description": stage["description"],
        "points": points,
        "progress": max(0.0, min(1.0, progress)),
        "points_to_next": max(0, points_to_next),
        "next_stage": next_stage["name"] if next_stage else None,
        "stats": {
            "total_memories": total_memories,
            "interactions": interactions,
            "concepts": concepts,
            "reflections": reflections,
            "turns": int(turns),
        },
    }


def format_growth(profile):
    stats = profile["stats"]
    lines = [
        f"Growth stage: {profile['stage']}",
        profile["description"],
        f"Growth points: {profile['points']}",
        f"Memories: {stats['total_memories']} total | {stats['interactions']} chats | {stats['concepts']} concepts | {stats['reflections']} reflections",
    ]
    if profile["next_stage"]:
        lines.append(f"Next stage: {profile['next_stage']} in {profile['points_to_next']} points")
    else:
        lines.append("Next stage: fully grown for now")
    return "\n".join(lines)
