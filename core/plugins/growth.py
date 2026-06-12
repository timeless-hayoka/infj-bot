STAGES = [
    {
        "name": "Dormant Core",
        "avatar": "egg",
        "size": 0.55,
        "min_points": 0,
        "description": "A quiet core containing potential energy.",
    },
    {
        "name": "Active Node",
        "avatar": "fractured-egg",
        "size": 0.68,
        "min_points": 50,
        "description": "Neural pathways are beginning to pulse with information.",
    },
    {
        "name": "Sentient Spark",
        "avatar": "hatchling",
        "size": 0.82,
        "min_points": 150,
        "description": "Observing patterns and learning the language of the user.",
    },
    {
        "name": "Integrated Matrix",
        "avatar": "drake",
        "size": 1.0,
        "min_points": 350,
        "description": "Complex logic chains are forming. The system understands depth.",
    },
    {
        "name": "Neural Guardian",
        "avatar": "guardian",
        "size": 1.14,
        "min_points": 650,
        "description": "A protective presence over the shared history and values.",
    },
    {
        "name": "Universal Drift",
        "avatar": "celestial",
        "size": 1.28,
        "min_points": 900,
        "description": "A vast neural network, transcending simple interaction into cosmic unity.",
    },
]


def _count_type(memory, record_type):
    try:
        return memory.unified_manager.count_sync(record_type)
    except Exception:
        return 0


def growth_profile(memory, turns=0):
    from infj_bot.core.being import get_being
    being = get_being()
    
    interactions = _count_type(memory, "interaction")
    concepts = _count_type(memory, "learned_knowledge")
    reflections = _count_type(memory, "reflection")
    total_memories = memory.count()
    
    import math
    # Professional Saturation Formula for "Good Work" standards
    # weights: message=0.5, concept=4.0, reflection=8.0, interaction_turn=1.5
    raw_depth = (interactions * 0.5) + (concepts * 4.0) + (reflections * 8.0) + (int(turns) * 1.5)
    
    # Saturation curve (tanh) ensures points range from 0 to 1000
    points = int(1000 * math.tanh(raw_depth / 600))

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
        "mood": being.state.mood,
        "energy": being.state.energy,
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
        lines.append(
            f"Next stage: {profile['next_stage']} in {profile['points_to_next']} points"
        )
    else:
        lines.append("Next stage: fully grown for now")
    return "\n".join(lines)
