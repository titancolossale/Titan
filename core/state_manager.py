# =====================================
# Titan State Manager
# =====================================

import json
import os


class StateManager:

    def __init__(self, file_path="data/titan_state.json"):
        self.file_path = file_path
        self.state = self.load_state()

    def load_state(self):
        if not os.path.exists(self.file_path):
            return {
                "active_project": "Titan",
                "current_step": "Développement du State Manager",
                "last_user_message": None,
                "last_titan_response": None,
                "next_action": "Connecter le State Manager au Brain",
                "progress": "En développement"
            }

        with open(self.file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def save_state(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(self.state, file, indent=4, ensure_ascii=False)

    def get_state(self):
        return self.state

    def update_state(self, key, value):
        self.state[key] = value
        self.save_state()

    def update_after_response(self, user_message, titan_response):
        self.state["last_user_message"] = user_message
        self.state["last_titan_response"] = titan_response
        self.save_state()

    def show_state(self):
        return json.dumps(self.state, indent=4, ensure_ascii=False)