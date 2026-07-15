/** Titan Frontend V2 — Production center panel layouts (Phase E2). */

import { CENTER_PANELS } from "../panel-slots.js";

/**
 * @param {string} title
 * @param {string} subtitle
 * @param {string} [emptyMessage]
 */
function createScreenPanel(title, subtitle, emptyMessage = "Rien à afficher pour le moment.") {
  const panel = document.createElement("section");
  panel.className = "tdl-v2-panel-view tdl-v2-panel-view--surface";
  panel.setAttribute("role", "region");

  const header = document.createElement("header");
  header.className = "tdl-v2-screen-header";
  header.innerHTML = `
    <h2 class="tdl-v2-screen-header__title">${title}</h2>
    <p class="tdl-v2-screen-header__subtitle">${subtitle}</p>
  `;

  const body = document.createElement("div");
  body.className = "tdl-v2-screen-body";
  body.innerHTML = `
    <div class="tdl-v2-empty-state">
      <div class="tdl-v2-empty-state__icon" aria-hidden="true"></div>
      <p>${emptyMessage}</p>
    </div>
  `;

  panel.append(header, body);
  return panel;
}

function createChatPanel() {
  const panel = document.createElement("section");
  panel.className = "tdl-v2-panel-view tdl-v2-panel-view--chat";
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-label", "Conversation");

  panel.innerHTML = `
    <div class="tdl-v2-conversation">
      <div class="tdl-v2-conversation__scroll" aria-live="polite">
        <div class="tdl-v2-conversation__inner" id="tdl-v2-chat-messages">
          <div class="tdl-v2-conversation__welcome" data-welcome="ambient" aria-hidden="true"></div>
        </div>
      </div>
      <p class="tdl-v2-conversation__thinking" id="tdl-v2-thinking-indicator" data-visible="false">
        Titan réfléchit…
      </p>
      <button type="button" class="tdl-v2-btn tdl-v2-btn--ghost tdl-v2-conversation__retry" id="tdl-v2-chat-retry" hidden>
        Réessayer le dernier message
      </button>
    </div>
  `;

  return panel;
}

function createVoicePanel() {
  const panel = createScreenPanel(
    "Voice",
    "Interaction vocale avec Titan",
    "Le mode vocal sera disponible ici.",
  );
  panel.classList.add("tdl-v2-panel-view--voice");
  return panel;
}

/** @param {import("./panel-registry.js").PanelRegistry} registry */
export function registerPanelLayouts(registry) {
  const definitions = {
    chat: { label: "Conversation", factory: createChatPanel },
    projects: {
      label: "Projects",
      factory: () =>
        createScreenPanel("Projects", "Projets et missions actives", "Aucun projet actif."),
    },
    memory: {
      label: "Mémoire",
      factory: () =>
        createScreenPanel("Mémoire", "Connaissance durable et rappels", "Aucune note récente."),
    },
    obsidian: {
      label: "Obsidian",
      factory: () =>
        createScreenPanel("Obsidian", "Vault personnel Titan AI", "Vault connecté — en attente."),
    },
    browser: {
      label: "Exploration",
      factory: () =>
        createScreenPanel("Exploration", "Recherche et navigation web", "Aucune exploration en cours."),
    },
    trading: {
      label: "Trading",
      factory: () =>
        createScreenPanel("Trading", "Marchés et exécution", "Module trading — bientôt disponible."),
    },
    calendar: {
      label: "Calendar",
      factory: () =>
        createScreenPanel("Calendar", "Agenda et rappels", "Module calendrier — bientôt disponible."),
    },
    tools: {
      label: "Tools",
      factory: () =>
        createScreenPanel("Tools", "Outils et capacités Titan", "Catalogue d'outils — bientôt disponible."),
    },
    voice: { label: "Voice", factory: createVoicePanel },
  };

  for (const id of CENTER_PANELS) {
    const def = definitions[id];
    if (!def) {
      continue;
    }
    registry.register({
      id,
      slot: "center",
      label: def.label,
      factory: def.factory,
    });
  }

  registry.register({
    id: "settings-overlay",
    slot: "overlay",
    label: "Paramètres",
    factory: () => {
      const el = document.createElement("div");
      el.className = "tdl-v2-settings-card";
      el.innerHTML = `
        <h2 class="tdl-v2-settings-card__title">Paramètres</h2>
        <p class="tdl-v2-settings-card__subtitle">Configuration Titan — interface V2.</p>
      `;
      return el;
    },
  });
}
