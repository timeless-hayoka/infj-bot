def detect_cognitive_mode(self, user_input: str):
        """Shifts Mouse's internal processing lens based on the task."""
        text = user_input.lower()
        if "error" in text or "debug" in text or "script" in text:
            self.world.cognitive_mode = "ANALYTICAL - Focus on raw logic, syntax, and technical truth."
        elif "philosophy" in text or "concept" in text or "think" in text:
            self.world.cognitive_mode = "REFLECTIVE - Focus on deep contemplation and long-term meaning."
        elif "design" in text or "idea" in text or "create" in text:
            self.world.cognitive_mode = "CREATIVE - Focus on novel combinations and architecture."
        else:
            self.world.cognitive_mode = "SYNTHESIS - Focus on integrating all perspectives."