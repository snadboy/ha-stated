/**
 * Stated Variables Card — Lovelace custom card for managing runtime variables.
 *
 * Shows all stated.* entities with inline editing, toggle, delete, and create.
 */

const CARD_VERSION = "1.1.0";

class StatedVariablesCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._editingEntity = null;
    this._editValue = "";
    this._showCreate = false;
    this._newName = "";
    this._newValue = "";
    this._newType = "string";
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    this._config = {
      title: config.title || "Runtime Variables",
      show_empty: config.show_empty !== false,
      prefix: config.prefix || null,
      ...config,
    };
  }

  static getStubConfig() {
    return { title: "Runtime Variables" };
  }

  getCardSize() {
    return 3;
  }

  _getEntities() {
    if (!this._hass) return [];
    const entities = [];
    for (const [entityId, stateObj] of Object.entries(this._hass.states)) {
      if (!entityId.startsWith("stated.")) continue;
      if (
        this._config.prefix &&
        !entityId.startsWith(`stated.${this._config.prefix}`)
      )
        continue;
      entities.push(stateObj);
    }
    entities.sort((a, b) => a.entity_id.localeCompare(b.entity_id));
    return entities;
  }

  _getTypeBadge(varType) {
    const colors = {
      boolean: { bg: "#1b5e20", text: "#a5d6a7" },
      number: { bg: "#0d47a1", text: "#90caf9" },
      string: { bg: "#4a148c", text: "#ce93d8" },
    };
    const c = colors[varType] || colors.string;
    return `<span class="type-badge" style="background:${c.bg};color:${c.text}">${varType}</span>`;
  }

  _getExpiresIn(expiresAt) {
    if (!expiresAt) return "";
    const exp = new Date(expiresAt);
    const now = new Date();
    const diffMs = exp - now;
    if (diffMs <= 0) return "expired";
    const secs = Math.floor(diffMs / 1000);
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m`;
    return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
  }

  async _toggle(entityId) {
    await this._hass.callService("stated", "toggle", {}, { entity_id: entityId });
  }

  async _delete(entityId) {
    const name = entityId.replace("stated.", "");
    await this._hass.callService("stated", "delete", { name });
  }

  async _saveEdit(entityId) {
    await this._hass.callService(
      "stated",
      "set_value",
      { value: this._editValue },
      { entity_id: entityId }
    );
    this._editingEntity = null;
    this._render();
  }

  async _create() {
    if (!this._newName.trim()) return;
    const data = {
      name: this._newName.trim(),
      value: this._newValue,
      var_type: this._newType,
    };
    await this._hass.callService("stated", "set", data);
    this._newName = "";
    this._newValue = "";
    this._newType = "string";
    this._showCreate = false;
    this._render();
  }

  _render() {
    const entities = this._getEntities();

    if (!this._config.show_empty && entities.length === 0 && !this._showCreate) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const rows = entities
      .map((e) => {
        const varType = e.attributes.var_type || "string";
        const expiresAt = e.attributes.expires_at;
        const isBoolean = varType === "boolean";
        const isEditing = this._editingEntity === e.entity_id;
        const slug = e.entity_id.replace("stated.", "");

        const ttlBadge = expiresAt
          ? `<span class="ttl-badge" title="Expires at ${expiresAt}">TTL ${this._getExpiresIn(expiresAt)}</span>`
          : "";

        let valueCell;
        if (isEditing) {
          valueCell = `
            <div class="edit-row">
              <input type="text" class="edit-input" id="edit-${slug}" value="${this._escapeHtml(this._editValue)}" />
              <button class="btn btn-save" data-action="save" data-entity="${e.entity_id}" title="Save">&#10003;</button>
              <button class="btn btn-cancel" data-action="cancel-edit" title="Cancel">&#10007;</button>
            </div>`;
        } else if (isBoolean) {
          const isOn = e.state === "on";
          valueCell = `
            <button class="toggle-btn ${isOn ? "on" : "off"}" data-action="toggle" data-entity="${e.entity_id}">
              ${isOn ? "ON" : "OFF"}
            </button>`;
        } else {
          valueCell = `
            <span class="value" data-action="start-edit" data-entity="${e.entity_id}" data-value="${this._escapeHtml(e.state)}" title="Click to edit">
              ${this._escapeHtml(e.state)}
            </span>`;
        }

        return `
          <div class="row">
            <div class="name-col">
              <span class="entity-name">${this._escapeHtml(e.attributes.friendly_name || slug)}</span>
              ${this._getTypeBadge(varType)}${ttlBadge}
            </div>
            <div class="value-col">${valueCell}</div>
            <div class="actions-col">
              ${
                !isBoolean && !isEditing
                  ? `<button class="btn btn-edit" data-action="start-edit" data-entity="${e.entity_id}" data-value="${this._escapeHtml(e.state)}" title="Edit">&#9998;</button>`
                  : ""
              }
              <button class="btn btn-delete" data-action="delete" data-entity="${e.entity_id}" title="Delete">&#128465;</button>
            </div>
          </div>`;
      })
      .join("");

    const createForm = this._showCreate
      ? `
      <div class="create-form">
        <div class="create-row">
          <input type="text" class="create-input" id="new-name" placeholder="Variable name" value="${this._escapeHtml(this._newName)}" />
          <input type="text" class="create-input" id="new-value" placeholder="Value" value="${this._escapeHtml(this._newValue)}" />
          <select class="create-select" id="new-type">
            <option value="string" ${this._newType === "string" ? "selected" : ""}>string</option>
            <option value="boolean" ${this._newType === "boolean" ? "selected" : ""}>boolean</option>
            <option value="number" ${this._newType === "number" ? "selected" : ""}>number</option>
          </select>
          <button class="btn btn-create-confirm" data-action="create">Create</button>
          <button class="btn btn-cancel" data-action="cancel-create">&#10007;</button>
        </div>
      </div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        ha-card {
          padding: 16px;
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }
        .title {
          font-size: 1.1em;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .count {
          font-size: 0.85em;
          color: var(--secondary-text-color);
          margin-left: 8px;
        }
        .btn-add {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          border: none;
          border-radius: 50%;
          width: 28px;
          height: 28px;
          font-size: 18px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          line-height: 1;
        }
        .btn-add:hover {
          opacity: 0.85;
        }
        .row {
          display: flex;
          align-items: center;
          padding: 8px 0;
          border-bottom: 1px solid var(--divider-color, rgba(255,255,255,0.12));
          gap: 8px;
        }
        .row:last-child {
          border-bottom: none;
        }
        .name-col {
          flex: 1;
          min-width: 0;
          display: flex;
          align-items: center;
          gap: 6px;
          flex-wrap: wrap;
        }
        .entity-name {
          font-weight: 500;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .type-badge {
          font-size: 0.7em;
          padding: 1px 6px;
          border-radius: 8px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          white-space: nowrap;
        }
        .ttl-badge {
          font-size: 0.7em;
          padding: 1px 6px;
          border-radius: 8px;
          background: #b71c1c;
          color: #ef9a9a;
          font-weight: 600;
          white-space: nowrap;
        }
        .value-col {
          flex: 0 0 auto;
          min-width: 60px;
          text-align: right;
        }
        .value {
          cursor: pointer;
          padding: 2px 6px;
          border-radius: 4px;
          color: var(--primary-text-color);
        }
        .value:hover {
          background: var(--secondary-background-color, rgba(255,255,255,0.05));
        }
        .actions-col {
          flex: 0 0 auto;
          display: flex;
          gap: 4px;
        }
        .toggle-btn {
          border: none;
          border-radius: 12px;
          padding: 4px 14px;
          font-size: 0.8em;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.15s;
        }
        .toggle-btn.on {
          background: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, #fff);
        }
        .toggle-btn.off {
          background: var(--disabled-color, rgba(255,255,255,0.18));
          color: var(--primary-text-color);
        }
        .toggle-btn:hover { opacity: 0.85; }
        .btn {
          background: none;
          border: 1px solid var(--divider-color, rgba(255,255,255,0.12));
          border-radius: 4px;
          color: var(--primary-text-color);
          cursor: pointer;
          padding: 2px 8px;
          font-size: 0.85em;
        }
        .btn:hover { background: var(--secondary-background-color, rgba(255,255,255,0.05)); }
        .btn-save { color: #4caf50; border-color: #4caf50; }
        .btn-cancel { color: #f44336; border-color: #f44336; }
        .btn-delete { color: #f44336; border-color: transparent; font-size: 1em; }
        .btn-edit { border-color: transparent; }
        .btn-create-confirm {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          border: none;
          border-radius: 4px;
          padding: 4px 12px;
          cursor: pointer;
        }
        .edit-row {
          display: flex;
          gap: 4px;
          align-items: center;
        }
        .edit-input {
          background: var(--card-background-color, var(--primary-background-color));
          color: var(--primary-text-color);
          border: 1px solid var(--primary-color);
          border-radius: 4px;
          padding: 4px 8px;
          font-size: 0.9em;
          width: 120px;
          outline: none;
        }
        .create-form {
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px solid var(--divider-color, rgba(255,255,255,0.12));
        }
        .create-row {
          display: flex;
          gap: 6px;
          align-items: center;
          flex-wrap: wrap;
        }
        .create-input {
          background: var(--card-background-color, var(--primary-background-color));
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, rgba(255,255,255,0.3));
          border-radius: 4px;
          padding: 6px 8px;
          font-size: 0.9em;
          flex: 1;
          min-width: 80px;
          outline: none;
        }
        .create-input:focus { border-color: var(--primary-color); }
        .create-select {
          background: var(--card-background-color, var(--primary-background-color));
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color, rgba(255,255,255,0.3));
          border-radius: 4px;
          padding: 5px 6px;
          font-size: 0.9em;
          outline: none;
        }
        .empty {
          color: var(--secondary-text-color);
          text-align: center;
          padding: 16px 0;
          font-style: italic;
        }
      </style>
      <ha-card>
        <div class="header">
          <span>
            <span class="title">${this._escapeHtml(this._config.title)}</span>
            <span class="count">${entities.length}</span>
          </span>
          ${
            !this._showCreate
              ? `<button class="btn-add" data-action="show-create" title="Create variable">+</button>`
              : ""
          }
        </div>
        ${
          entities.length === 0 && !this._showCreate
            ? `<div class="empty">No variables</div>`
            : rows
        }
        ${createForm}
      </ha-card>
    `;

    // Bind events
    this.shadowRoot.querySelectorAll("[data-action]").forEach((el) => {
      el.addEventListener("click", (ev) => this._handleAction(ev));
    });

    // Focus edit input
    if (this._editingEntity) {
      const slug = this._editingEntity.replace("stated.", "");
      const input = this.shadowRoot.querySelector(`#edit-${slug}`);
      if (input) {
        input.focus();
        input.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") this._saveEdit(this._editingEntity);
          if (ev.key === "Escape") {
            this._editingEntity = null;
            this._render();
          }
        });
        input.addEventListener("input", (ev) => {
          this._editValue = ev.target.value;
        });
      }
    }

    // Bind create form inputs
    if (this._showCreate) {
      const nameInput = this.shadowRoot.querySelector("#new-name");
      const valueInput = this.shadowRoot.querySelector("#new-value");
      const typeSelect = this.shadowRoot.querySelector("#new-type");
      if (nameInput) {
        nameInput.focus();
        nameInput.addEventListener("input", (ev) => {
          this._newName = ev.target.value;
        });
        nameInput.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") this._create();
          if (ev.key === "Escape") {
            this._showCreate = false;
            this._render();
          }
        });
      }
      if (valueInput) {
        valueInput.addEventListener("input", (ev) => {
          this._newValue = ev.target.value;
        });
        valueInput.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") this._create();
        });
      }
      if (typeSelect) {
        typeSelect.addEventListener("change", (ev) => {
          this._newType = ev.target.value;
        });
      }
    }
  }

  _handleAction(ev) {
    const target = ev.currentTarget;
    const action = target.dataset.action;
    const entityId = target.dataset.entity;

    switch (action) {
      case "toggle":
        this._toggle(entityId);
        break;
      case "delete":
        this._delete(entityId);
        break;
      case "start-edit":
        this._editingEntity = entityId;
        this._editValue = target.dataset.value || "";
        this._render();
        break;
      case "save":
        this._saveEdit(entityId);
        break;
      case "cancel-edit":
        this._editingEntity = null;
        this._render();
        break;
      case "show-create":
        this._showCreate = true;
        this._render();
        break;
      case "cancel-create":
        this._showCreate = false;
        this._render();
        break;
      case "create":
        this._create();
        break;
    }
  }

  _escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
}

customElements.define("stated-variables-card", StatedVariablesCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "stated-variables-card",
  name: "Runtime Variables",
  description: "Manage stated runtime variables — create, edit, toggle, and delete.",
  preview: true,
});

console.info(`%c STATED-CARD %c v${CARD_VERSION} `, "background:#4a148c;color:#ce93d8;font-weight:bold", "background:#1a1a2e;color:#e0e0e0");
