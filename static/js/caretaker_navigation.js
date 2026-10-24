(() => {
  const initialize = () => {
    const sidebar = document.querySelector('.sidebar');
    const topbar = document.querySelector('.topbar');
    if (!sidebar || !topbar || topbar.querySelector('.caretaker-menu-toggle')) return;
    if (sidebar.parentElement === document.body) {
      document.body.classList.add('caretaker-direct-layout');
    }

    const toggle = document.createElement('button');
    toggle.className = 'caretaker-menu-toggle';
    toggle.type = 'button';
    toggle.setAttribute('aria-label', 'Open navigation menu');
    toggle.setAttribute('aria-controls', 'caretaker-sidebar');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.innerHTML = '<span></span><span></span><span></span>';
    topbar.insertBefore(toggle, topbar.firstChild);
    sidebar.id = 'caretaker-sidebar';

    let backdrop = document.querySelector('.caretaker-drawer-backdrop');
    if (!backdrop) {
      backdrop = document.createElement('button');
      backdrop.className = 'caretaker-drawer-backdrop';
      backdrop.type = 'button';
      backdrop.setAttribute('aria-label', 'Close navigation menu');
      sidebar.insertAdjacentElement('afterend', backdrop);
    }

    const close = () => {
      sidebar.classList.remove('is-open');
      backdrop.classList.remove('is-visible');
      document.body.classList.remove('caretaker-menu-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open navigation menu');
    };
    const open = () => {
      sidebar.classList.add('is-open');
      backdrop.classList.add('is-visible');
      document.body.classList.add('caretaker-menu-open');
      toggle.setAttribute('aria-expanded', 'true');
      toggle.setAttribute('aria-label', 'Close navigation menu');
    };

    toggle.addEventListener('click', () => {
      if (sidebar.classList.contains('is-open')) close();
      else open();
    });
    backdrop.addEventListener('click', close);
    sidebar.querySelectorAll('a').forEach((link) => link.addEventListener('click', close));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') close();
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
  } else {
    initialize();
  }
})();
