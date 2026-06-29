# Titan Blueprint

## 1. Vision

Titan est un agentic AI personnel construit pour aider Nolan Hassing à gérer ses projets, apprendre, coder, analyser les marchés, automatiser des tâches et éventuellement automatiser certaines stratégies de trading.

Titan doit être construit comme un vrai logiciel professionnel, pas comme un simple chatbot.

## 2. Règle principale du projet

Tout ce qui est écrit dans VS Code doit avoir une vraie utilité dans la version finale de Titan.

Pas de code inutile.
Pas de faux exercices.
Pas de fichiers temporaires sans rôle clair.

## 3. Personnalité de Titan

À définir plus tard dans le module prompts.

Titan devra avoir une personnalité :
- calme
- intelligent
- loyal
- direct
- discipliné
- professionnel
- protecteur
- orienté action

## 4. Architecture actuelle

Titan/
- main.py
- config/settings.py
- agents/
- brain/
- memory/
- tools/
- prompts/
- data/
- logs/
- tests/

## 5. État actuel

Version actuelle : **0.1.0** (Phase 1 — Architecture Cleanup, juin 2026)

Fondations terminées :

- Composition root unique (`core/titan.py`) avec injection de dépendances — une instance partagée par manager (`AgentManager`, `ContextManager`, `StateManager`, `MissionManager`, `LongTermMemory`)
- Chemin d'orchestration agent unique — exécution via `Brain.think()` → `TaskOrchestrator` uniquement
- Corrections P0 (Brain Audit) — double exécution agents, faux positifs TaskEvaluator, gestion d'erreurs REPL/LLM
- Gating de création de mission — missions explicites seulement
- Suppression des modules morts (`core/action_manager.py`, `core/context.py`)
- Logging structuré (`logs/`, `core/logging_config.py`)
- Suite de tests de régression (`tests/` — 110 tests)
- Stub `MemoryFacade` câblé au composition root

Non inclus dans 0.1.0 (phases ultérieures) : agents LLM réels, constitution/identité dans les prompts, mémoire unifiée complète, outils Brain, trading, API/voice.

## 6. Prochaines étapes

1. Finaliser le Blueprint
2. Créer le système de logs
3. Créer le noyau brain
4. Créer la mémoire
5. Connecter Claude
6. Ajouter les premiers outils
7. Construire le module trading