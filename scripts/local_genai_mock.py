class SimpleResponse:
    def __init__(self, text):
        self.text = text


# Marker for caller to detect this is a lightweight local mock
IS_LOCAL_MOCK = True


class Chat:
    def __init__(self, model, history=None):
        self.model = model
        self.history = history or []

    def send_message(self, user_input):
        reply = f"[MOCK {self.model.model_name}] Echo: {user_input}"
        return SimpleResponse(reply)


class GenerativeModel:
    def __init__(self, model_name, system_instruction=None):
        self.model_name = model_name
        self.system_instruction = system_instruction

    def generate_content(self, prompt):
        return SimpleResponse(
            f"[MOCK {self.model_name}] Generated from prompt: {str(prompt)[:500]}"
        )

    def start_chat(self, history=None):
        return Chat(self, history)


_api_key = None


def configure(api_key=None):
    global _api_key
    _api_key = api_key


class Client:
    def __init__(self, api_key=None):
        self.api_key = api_key
        # for compatibility with code that expects client.models.generate_content
        self.models = self

    def generate_content(self, model=None, contents=None, config=None):
        txt = f"[MOCK CLIENT {model}] {str(contents)[:500]}"
        return SimpleResponse(txt)
