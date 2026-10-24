(() => {
  function initializeOwnerNavigation() {
    document.querySelectorAll('.app > .sidebar + .main > .topnav').forEach(header => {
      const app = header.closest('.app');
      const sidebar = app?.querySelector(':scope > .sidebar');
      if (!app || !sidebar) return;

      sidebar.id ||= 'owner-sidebar';
      const quickLinks = header.querySelector('.topnav-links');
      if (quickLinks && !sidebar.querySelector('.owner-mobile-quicklinks')) {
        const mobileQuickLinks = quickLinks.cloneNode(true);
        mobileQuickLinks.className = 'owner-mobile-quicklinks';
        mobileQuickLinks.setAttribute('aria-label', 'Owner shortcuts');
        sidebar.insertBefore(mobileQuickLinks, sidebar.querySelector('.logout'));
      }

      let toggle = header.querySelector('.owner-menu-toggle');
      if (!toggle) {
        toggle = document.createElement('button');
        toggle.className = 'owner-menu-toggle';
        toggle.type = 'button';
        toggle.setAttribute('aria-label', 'Open owner navigation');
        toggle.setAttribute('aria-controls', sidebar.id);
        toggle.setAttribute('aria-expanded', 'false');
        toggle.innerHTML = '<span></span><span></span><span></span>';
        header.prepend(toggle);
      }

      let backdrop = app.querySelector(':scope > .owner-menu-backdrop');
      if (!backdrop) {
        backdrop = document.createElement('button');
        backdrop.className = 'owner-menu-backdrop';
        backdrop.type = 'button';
        backdrop.setAttribute('aria-label', 'Close owner navigation');
        backdrop.tabIndex = -1;
        app.insertBefore(backdrop, sidebar.nextSibling);
      }

      const setOpen = open => {
        app.classList.toggle('owner-menu-open', open);
        toggle.setAttribute('aria-expanded', String(open));
        toggle.setAttribute('aria-label', open ? 'Close owner navigation' : 'Open owner navigation');
        if (open && window.innerWidth <= 1024) {
          app.dataset.previousBodyOverflow = document.body.style.overflow;
          document.body.style.overflow = 'hidden';
        } else if (!open) {
          document.body.style.overflow = app.dataset.previousBodyOverflow || '';
          delete app.dataset.previousBodyOverflow;
        }
      };

      toggle.addEventListener('click', () => {
        const open = !app.classList.contains('owner-menu-open');
        setOpen(open);
        if (open) sidebar.querySelector('a')?.focus();
      });
      backdrop.addEventListener('click', () => {
        setOpen(false);
        toggle.focus();
      });
      sidebar.addEventListener('click', event => {
        if (event.target.closest('a')) setOpen(false);
      });
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && app.classList.contains('owner-menu-open')) {
          setOpen(false);
          toggle.focus();
        }
      });
      window.addEventListener('resize', () => {
        if (window.innerWidth > 1024) setOpen(false);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeOwnerNavigation, { once: true });
  } else {
    initializeOwnerNavigation();
  }
})();
