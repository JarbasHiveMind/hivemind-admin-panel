// hivemind-admin-panel — lightweight i18n scaffold.
// Strings are externalized progressively; tag elements with data-i18n="key".
const I18N = {
  en: {
    dashboard: 'Dashboard', clients: 'Clients', acl: 'Permissions', personas: 'Personas',
    chat: 'Test Chat', agents: 'Agent Protocol', database: 'Database', network: 'Network',
    voice: 'OpenVoiceOS Plugins', binary: 'Binary Protocol', presets: 'Presets', encodings: 'Encodings',
    monitor: 'Monitor', topology: 'Topology', servers: 'OVOS Servers',
    operations: 'Operations', logout: 'Logout', refresh: 'Refresh', language: 'Language'
  },
  es: {
    dashboard: 'Panel', clients: 'Clientes', acl: 'Permisos', personas: 'Personas',
    chat: 'Chat de prueba', agents: 'Protocolo de agente', database: 'Base de datos', network: 'Red',
    voice: 'Plugins de OpenVoiceOS', binary: 'Protocolo binario', presets: 'Preajustes', encodings: 'Codificaciones',
    monitor: 'Monitor', topology: 'Topología', servers: 'Servidores OVOS',
    operations: 'Operaciones', logout: 'Salir', refresh: 'Actualizar', language: 'Idioma'
  },
  pt: {
    dashboard: 'Painel', clients: 'Clientes', acl: 'Permissões', personas: 'Personas',
    chat: 'Chat de teste', agents: 'Protocolo de agente', database: 'Base de dados', network: 'Rede',
    voice: 'Plugins do OpenVoiceOS', binary: 'Protocolo binário', presets: 'Predefinições', encodings: 'Codificações',
    monitor: 'Monitor', topology: 'Topologia', servers: 'Servidores OVOS',
    operations: 'Operações', logout: 'Sair', refresh: 'Atualizar', language: 'Idioma'
  }
};

let CURRENT_LANG = (typeof localStorage !== 'undefined' && localStorage.getItem('lang')) || 'en';

function t(key) {
  return (I18N[CURRENT_LANG] && I18N[CURRENT_LANG][key]) || I18N.en[key] || key;
}

function setLang(lang) {
  CURRENT_LANG = lang;
  try { localStorage.setItem('lang', lang); } catch (e) {}
  applyI18n();
}

function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  const sel = document.getElementById('langSelect');
  if (sel) sel.value = CURRENT_LANG;
}

document.addEventListener('DOMContentLoaded', applyI18n);
