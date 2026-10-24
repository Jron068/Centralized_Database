(() => {
  function createToggle(className, controls, label) {
    const button = document.createElement('button');
    button.className = className;
    button.type = 'button';
    button.setAttribute('aria-label', label);
    button.setAttribute('aria-controls', controls);
    button.setAttribute('aria-expanded', 'false');
    button.innerHTML = '<span></span><span></span><span></span>';
    return button;
  }

  function initializeNavigation() {
    document.querySelectorAll('body > header').forEach(header => {
      const nav = header.querySelector(':scope > nav');
      if (!nav) return;

      header.classList.add('site-header');
      nav.id ||= 'site-navigation';
      let toggle = header.querySelector('.site-menu-toggle');
      if (!toggle) {
        toggle = createToggle('site-menu-toggle', nav.id, 'Open navigation menu');
        header.prepend(toggle);
      }

      toggle.addEventListener('click', () => {
        const isOpen = header.classList.toggle('menu-open');
        toggle.setAttribute('aria-expanded', String(isOpen));
        toggle.setAttribute('aria-label', isOpen ? 'Close navigation menu' : 'Open navigation menu');
      });

      nav.addEventListener('click', event => {
        if (event.target.closest('a')) {
          header.classList.remove('menu-open');
          toggle.setAttribute('aria-expanded', 'false');
        }
      });
    });

    document.querySelectorAll('.app > .sidebar + .main > .topbar, .layout > .sidebar + .main > .topbar').forEach(header => {
      const navigation = header.querySelector('.topbar-links');
      const app = header.closest('.app, .layout');
      const sidebar = app?.querySelector(':scope > .sidebar');
      if (!navigation || !app || !sidebar) return;

      navigation.id ||= 'customer-top-navigation';
      sidebar.id ||= 'customer-sidebar';
      let toggle = header.querySelector('.customer-menu-toggle');
      if (!toggle) {
        toggle = createToggle('customer-menu-toggle', `${navigation.id} ${sidebar.id}`, 'Open customer navigation');
        header.prepend(toggle);
      }

      toggle.addEventListener('click', () => {
        const isOpen = app.classList.toggle('customer-menu-open');
        toggle.setAttribute('aria-expanded', String(isOpen));
        toggle.setAttribute('aria-label', isOpen ? 'Close customer navigation' : 'Open customer navigation');
      });

      app.querySelectorAll('.sidebar a, .topbar-links a').forEach(link => {
        link.addEventListener('click', () => {
          app.classList.remove('customer-menu-open');
          toggle.setAttribute('aria-expanded', 'false');
        });
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeNavigation, { once: true });
  } else {
    initializeNavigation();
  }
})();
