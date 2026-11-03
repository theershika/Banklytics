'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('menu-toggle');
  const backdrop = document.getElementById('sidebar-backdrop');
  function setMenu(open) { sidebar?.classList.toggle('open', open); backdrop?.classList.toggle('show', open); toggle?.setAttribute('aria-expanded', String(open)); }
  toggle?.addEventListener('click', () => setMenu(!sidebar.classList.contains('open')));
  backdrop?.addEventListener('click', () => setMenu(false));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') setMenu(false); });
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', e => { if (!window.confirm(form.dataset.confirm)) e.preventDefault(); }));
  document.querySelectorAll('form[data-submit-once]').forEach(form => form.addEventListener('submit', e => {
    if (e.defaultPrevented || !form.checkValidity()) return;
    if (form.dataset.submitting === 'yes') { e.preventDefault(); return; }
    form.dataset.submitting = 'yes';
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; button.setAttribute('aria-busy','true'); button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Processing…'; }
  }));
  document.querySelectorAll('[data-toggle-password]').forEach(button => button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.togglePassword); const show = input.type === 'password';
    input.type = show ? 'text' : 'password'; button.innerHTML = '<i class="bi bi-eye' + (show ? '-slash' : '') + '"></i>'; button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  }));
  document.querySelectorAll('[data-amount]').forEach(button => button.addEventListener('click', () => {
    const input = document.getElementById('amount'); input.value = button.dataset.amount; input.dispatchEvent(new Event('input')); input.focus();
  }));
});
