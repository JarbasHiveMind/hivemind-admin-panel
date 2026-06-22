// hivemind-admin-panel — lightweight i18n scaffold.
// Strings are externalized progressively; tag elements with data-i18n="key".
const I18N = {
  en: {
    dashboard: 'Dashboard', clients: 'Clients', acl: 'ACL', personas: 'Personas',
    agents: 'Agents', database: 'Database', network: 'Network', voice: 'Voice Plugins',
    binary: 'Binary Protocol', encodings: 'Encodings', monitor: 'Monitor',
    topology: 'Topology', servers: 'OVOS Servers', operations: 'Operations',
    refresh: 'Refresh', language: 'Language'
  },
  es: {
    dashboard: 'Panel', clients: 'Clientes', acl: 'ACL', personas: 'Personas',
    agents: 'Agentes', database: 'Base de datos', network: 'Red', voice: 'Plugins de voz',
    binary: 'Protocolo binario', encodings: 'Codificaciones', monitor: 'Monitor',
    topology: 'Topología', servers: 'Servidores OVOS', operations: 'Operaciones',
    refresh: 'Actualizar', language: 'Idioma'
  },
  pt: {
    dashboard: 'Painel', clients: 'Clientes', acl: 'ACL', personas: 'Personas',
    agents: 'Agentes', database: 'Base de dados', network: 'Rede', voice: 'Plugins de voz',
    binary: 'Protocolo binário', encodings: 'Codificações', monitor: 'Monitor',
    topology: 'Topologia', servers: 'Servidores OVOS', operations: 'Operações',
    refresh: 'Atualizar', language: 'Idioma'
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
