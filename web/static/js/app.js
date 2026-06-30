// API utilities
const API = {
  async request(url, options = {}) {
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Request failed');
      }

      return await response.json();
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  },

  subscriptions: {
    async list() {
      return await API.request('/api/subscriptions');
    },
    async add(name, url, template) {
      return await API.request('/api/subscriptions', {
        method: 'POST',
        body: JSON.stringify({ name, url, template }),
      });
    },
    async remove(name) {
      return await API.request(`/api/subscriptions/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      });
    },
    async activate(name) {
      return await API.request(`/api/subscriptions/${encodeURIComponent(name)}/activate`, {
        method: 'POST',
      });
    },
    async update(name) {
      return await API.request(`/api/subscriptions/${encodeURIComponent(name)}/update`, {
        method: 'POST',
      });
    },
  },

  health: {
    async check() {
      return await API.request('/api/health');
    },
  },

  config: {
    async get() {
      return await API.request('/api/config');
    },
  },
};

// UI utilities
const UI = {
  showAlert(message, type = 'info') {
    const alertContainer = document.getElementById('alert-container');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
      <span>${this.getAlertIcon(type)}</span>
      <span>${message}</span>
    `;

    alertContainer.appendChild(alert);

    setTimeout(() => {
      alert.remove();
    }, 5000);
  },

  getAlertIcon(type) {
    const icons = {
      success: '✓',
      error: '✕',
      warning: '⚠',
      info: 'ℹ',
    };
    return icons[type] || icons.info;
  },

  showModal(id) {
    document.getElementById(id).classList.remove('hidden');
  },

  hideModal(id) {
    document.getElementById(id).classList.add('hidden');
  },

  showLoading(buttonId) {
    const button = document.getElementById(buttonId);
    button.disabled = true;
    button.innerHTML = '<span class="spinner"></span> Loading...';
  },

  hideLoading(buttonId, originalText) {
    const button = document.getElementById(buttonId);
    button.disabled = false;
    button.innerHTML = originalText;
  },
};

// State management
const State = {
  subscriptions: [],
  activeSubscription: null,
  health: null,
  config: null,
};

// Subscription management
const SubscriptionManager = {
  async load() {
    try {
      const response = await API.subscriptions.list();
      State.subscriptions = response.subscriptions;
      State.activeSubscription = response.active;
      this.render();
    } catch (error) {
      UI.showAlert(`Failed to load subscriptions: ${error.message}`, 'error');
    }
  },

  render() {
    const container = document.getElementById('subscriptions-list');

    if (State.subscriptions.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📡</div>
          <div class="empty-state-text">No subscriptions yet</div>
          <button class="btn btn-primary" onclick="SubscriptionManager.showAddModal()">
            Add Subscription
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Nodes</th>
              <th>Last Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            ${State.subscriptions.map(sub => this.renderRow(sub)).join('')}
          </tbody>
        </table>
      </div>
    `;
  },

  renderRow(sub) {
    const isActive = sub.name === State.activeSubscription;
    const statusBadge = isActive
      ? '<span class="badge badge-success">Active</span>'
      : '<span class="badge badge-info">Inactive</span>';

    const nodeCount = sub.node_count || 0;
    const lastUpdate = sub.last_update
      ? new Date(sub.last_update).toLocaleString()
      : 'Never';

    return `
      <tr>
        <td><strong>${sub.name}</strong></td>
        <td>${statusBadge}</td>
        <td>${nodeCount} nodes</td>
        <td class="text-muted">${lastUpdate}</td>
        <td>
          ${!isActive ? `
            <button class="btn btn-sm btn-secondary" onclick="SubscriptionManager.activate('${sub.name}')">
              Activate
            </button>
          ` : ''}
          <button class="btn btn-sm btn-primary" onclick="SubscriptionManager.update('${sub.name}')">
            Update
          </button>
          <button class="btn btn-sm btn-danger" onclick="SubscriptionManager.confirmRemove('${sub.name}')">
            Remove
          </button>
        </td>
      </tr>
    `;
  },

  showAddModal() {
    document.getElementById('add-form').reset();
    UI.showModal('add-modal');
  },

  async add() {
    const name = document.getElementById('sub-name').value.trim();
    const url = document.getElementById('sub-url').value.trim();
    const template = document.getElementById('sub-template').value;

    if (!name || !url) {
      UI.showAlert('Name and URL are required', 'error');
      return;
    }

    UI.showLoading('add-btn');

    try {
      await API.subscriptions.add(name, url, template);
      UI.showAlert('Subscription added successfully', 'success');
      UI.hideModal('add-modal');
      await this.load();
    } catch (error) {
      UI.showAlert(`Failed to add subscription: ${error.message}`, 'error');
    } finally {
      UI.hideLoading('add-btn', 'Add Subscription');
    }
  },

  confirmRemove(name) {
    State.toRemove = name;
    document.getElementById('remove-name').textContent = name;
    UI.showModal('remove-modal');
  },

  async remove() {
    const name = State.toRemove;

    UI.showLoading('remove-btn');

    try {
      await API.subscriptions.remove(name);
      UI.showAlert('Subscription removed successfully', 'success');
      UI.hideModal('remove-modal');
      await this.load();
    } catch (error) {
      UI.showAlert(`Failed to remove subscription: ${error.message}`, 'error');
    } finally {
      UI.hideLoading('remove-btn', 'Remove');
    }
  },

  async activate(name) {
    try {
      await API.subscriptions.activate(name);
      UI.showAlert(`Activated subscription: ${name}`, 'success');
      await this.load();
    } catch (error) {
      UI.showAlert(`Failed to activate subscription: ${error.message}`, 'error');
    }
  },

  async update(name) {
    UI.showAlert(`Updating subscription: ${name}...`, 'info');

    try {
      const result = await API.subscriptions.update(name);
      UI.showAlert(
        `Subscription updated: ${result.node_count} nodes (${result.type})`,
        'success'
      );
      await this.load();
    } catch (error) {
      UI.showAlert(`Failed to update subscription: ${error.message}`, 'error');
    }
  },
};

// Health check
const HealthMonitor = {
  async check() {
    try {
      const response = await API.health.check();
      State.health = response.health;
      this.render();
    } catch (error) {
      UI.showAlert(`Health check failed: ${error.message}`, 'error');
    }
  },

  render() {
    const container = document.getElementById('health-status');

    if (!State.health) {
      container.innerHTML = '<p class="text-muted">Loading health status...</p>';
      return;
    }

    const summary = State.health.summary;
    const checks = State.health.checks;

    const summaryBadge = summary.failed === 0
      ? '<span class="badge badge-success">✓ All systems operational</span>'
      : `<span class="badge badge-warning">⚠ ${summary.failed} check(s) failed</span>`;

    container.innerHTML = `
      <div class="mb-md">
        ${summaryBadge}
        <span class="text-muted">
          ${summary.passed} passed, ${summary.failed} failed, ${summary.total} total
        </span>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Status</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            ${checks.map(check => this.renderCheckRow(check)).join('')}
          </tbody>
        </table>
      </div>
    `;
  },

  renderCheckRow(check) {
    const statusBadge = check.passed
      ? '<span class="badge badge-success">✓ OK</span>'
      : '<span class="badge badge-error">✕ Failed</span>';

    return `
      <tr>
        <td><strong>${check.name}</strong></td>
        <td>${statusBadge}</td>
        <td class="text-muted">${check.message || '-'}</td>
      </tr>
    `;
  },
};

// Configuration
const ConfigManager = {
  async load() {
    try {
      const response = await API.config.get();
      State.config = response.config;
      this.updateDashboardUrl();
    } catch (error) {
      console.error('Failed to load config:', error);
    }
  },

  updateDashboardUrl() {
    if (!State.config) return;

    const dashboardUrl = `http://clash.razord.top/?hostname=127.0.0.1&port=${State.config.clash_api_port}&secret=`;
    document.getElementById('dashboard-frame').src = dashboardUrl;
  },
};

// Navigation
const Navigation = {
  currentView: 'subscriptions',

  init() {
    document.querySelectorAll('[data-view]').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        this.switchView(link.dataset.view);
      });
    });
  },

  switchView(view) {
    // Update active nav item
    document.querySelectorAll('[data-view]').forEach(link => {
      link.classList.toggle('active', link.dataset.view === view);
    });

    // Hide all views
    document.querySelectorAll('.view').forEach(v => {
      v.classList.add('hidden');
    });

    // Show selected view
    document.getElementById(`${view}-view`).classList.remove('hidden');
    this.currentView = view;

    // Refresh data for the view
    if (view === 'subscriptions') {
      SubscriptionManager.load();
    } else if (view === 'health') {
      HealthMonitor.check();
    }
  },
};

// Initialize app
async function init() {
  Navigation.init();

  // Load initial data
  await ConfigManager.load();
  await SubscriptionManager.load();
  await HealthMonitor.check();

  // Auto-refresh health every 30 seconds
  setInterval(() => {
    if (Navigation.currentView === 'health') {
      HealthMonitor.check();
    }
  }, 30000);
}

// Start app when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
