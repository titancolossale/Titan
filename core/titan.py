# ==========================================
# Titan Core
# ==========================================

import logging

from config.settings import DEBUG_BRAIN, TITAN_NAME, VERSION, CREATOR
from brain.autonomy_policy import AutonomyPolicy
from memory.memory_manager import MemoryManager
from memory.memory_service import MemoryService
from memory.long_term_memory import LongTermMemory
from memory.learning_memory import LearningMemory
from brain.brain import Brain
from tools.tool_manager import ToolManager
from context.context_manager import ContextManager
from core.conversation import Conversation
from core.conversation_engine import ConversationEngine
from core.state_manager import StateManager
from core.mission_manager import MissionManager
from core.job_store import JobStore
from core.scheduler import Scheduler
from core.job_runner import JobRunner
from agents.agent_manager import AgentManager

logger = logging.getLogger(__name__)


class Titan:

    def __init__(self):
        # Config / identity
        self.name = TITAN_NAME
        self.version = VERSION
        self.creator = CREATOR
        self.status = "OFFLINE"

        # Shared managers (composition root — single instance each)
        long_term = LongTermMemory()
        self.memory = MemoryService(
            short_term=MemoryManager(),
            long_term=long_term,
        )
        self.autonomy_policy = AutonomyPolicy.from_settings()
        self.learning_memory = LearningMemory()
        self.agents = AgentManager(
            memory_service=self.memory,
            autonomy_policy=self.autonomy_policy,
        )
        self.state = StateManager()
        self.mission = MissionManager()
        self.context = ContextManager(
            state_manager=self.state,
            mission_manager=self.mission,
        )
        self.tools = ToolManager()

        job_store = JobStore()
        self.scheduler = Scheduler(
            store=job_store,
            policy=self.autonomy_policy,
        )
        self.job_runner = JobRunner(self.scheduler)

        conversation_engine = ConversationEngine(
            session_id=self.context.session.session_id,
        )
        self.conversation = Conversation(engine=conversation_engine)

        # Brain receives injected managers
        self.brain = Brain(
            agent_manager=self.agents,
            context_manager=self.context,
            state_manager=self.state,
            mission_manager=self.mission,
            memory_service=self.memory,
            tool_manager=self.tools,
            conversation_engine=conversation_engine,
            autonomy_policy=self.autonomy_policy,
            learning_memory=self.learning_memory,
        )

        # Auxiliary subsystems — conversation engine shared with Brain above

    @property
    def long_memory(self) -> LongTermMemory:
        """Backward-compatible long-term memory access (P3-040)."""
        return self.memory.long_term

    def start(self):
     self.status = "ONLINE"
     self.memory.remember_session("Titan a démarré avec succès.")
     self.memory.show_session_memory()

     print("======================================")
     print(f"{self.name} AI v{self.version}")
     print(f"Créé par {self.creator}")
     print(f"Statut : {self.status}")
     print("======================================\n")

     if DEBUG_BRAIN:
         current_time = self.tools.get_current_time()
         context = self.context.get_context()
         logger.debug("Heure actuelle : %s", current_time)
         logger.debug("Contexte actuel :\n%s", context)

     current_user = self.context.current_user
     print(f"Bonjour {current_user}.")
     print(f"Je suis {self.name}.")
     print("Tous les systèmes sont opérationnels.")
     print("Comment puis-je t'aider aujourd'hui ?")

     while True:
        question = input("Toi : ")

        if question.lower() in ["exit", "quit", "stop", "bye"]:
            print(f"Titan : Session terminée. À bientôt {self.context.current_user}.")
            break

        self.conversation.add_message(self.context.current_user, question)

        try:
            reponse = self.brain.think(question)
        except Exception:
            logger.exception("Brain failure")
            reponse = "Désolé, une erreur interne s'est produite. On peut réessayer."

        self.conversation.add_message("Titan", reponse)

        print(reponse)
        print()
