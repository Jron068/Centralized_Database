(() => {
  if (document.querySelector('.welcome-music')) return;

  const loginMusicRequested = new URL(window.location.href).searchParams.get('welcome_music') === '1';
  if (loginMusicRequested) {
    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete('welcome_music');
    window.history.replaceState(window.history.state, '', cleanUrl);
    sessionStorage.setItem('welcomeMusicPlaying', '1');
  }
  const shouldResumeMusic = loginMusicRequested || sessionStorage.getItem('welcomeMusicPlaying') === '1';

  const audio = document.createElement('audio');
  audio.loop = true;
  audio.preload = 'auto';
  audio.autoplay = shouldResumeMusic;
  const savedVolume = Number(localStorage.getItem('welcomeMusicVolume'));
  audio.volume = Number.isFinite(savedVolume) ? Math.max(0, Math.min(.5, savedVolume)) : .22;

  const player = document.createElement('aside');
  player.className = 'welcome-music';
  player.setAttribute('aria-label', 'Welcome music player');
  player.innerHTML = `
    <button class="welcome-music-toggle" type="button" aria-label="Play welcome music" title="Play welcome music">
      <span aria-hidden="true">&#9654;</span>
    </button>
    <div class="welcome-music-copy"><strong>Welcome music</strong><span class="welcome-music-state">Paused</span></div>
    <label class="welcome-music-volume-label" aria-label="Music volume">
      <span aria-hidden="true">&#9834;</span>
      <input class="welcome-music-volume" type="range" min="0" max="0.5" step="0.01" aria-label="Music volume">
    </label>`;
  document.body.append(player, audio);

  const toggle = player.querySelector('.welcome-music-toggle');
  const icon = toggle.querySelector('span');
  const state = player.querySelector('.welcome-music-state');
  const volume = player.querySelector('.welcome-music-volume');
  volume.value = String(audio.volume);

  function setPlaying(isPlaying) {
    icon.innerHTML = isPlaying ? '&#10074;&#10074;' : '&#9654;';
    const label = isPlaying ? 'Pause welcome music' : 'Play welcome music';
    toggle.setAttribute('aria-label', label);
    toggle.title = label;
    state.textContent = isPlaying ? 'Playing' : 'Paused';
    player.classList.toggle('is-playing', isPlaying);
  }

  function savePosition() {
    if (Number.isFinite(audio.currentTime)) {
      sessionStorage.setItem('welcomeMusicPosition', String(audio.currentTime));
    }
  }

  async function startPlayback() {
    try {
      await audio.play();
      sessionStorage.setItem('welcomeMusicPlaying', '1');
      setPlaying(true);
    } catch (_error) {
      setPlaying(false);
      state.textContent = 'Tap to resume';
    }
  }

  toggle.addEventListener('click', () => {
    if (audio.paused) startPlayback();
    else {
      audio.pause();
      sessionStorage.setItem('welcomeMusicPlaying', '0');
      setPlaying(false);
    }
  });

  volume.addEventListener('input', () => {
    audio.volume = Number(volume.value);
    localStorage.setItem('welcomeMusicVolume', volume.value);
  });

  audio.addEventListener('play', () => setPlaying(true));
  audio.addEventListener('pause', () => setPlaying(false));
  audio.addEventListener('timeupdate', () => {
    if (Number.isFinite(audio.currentTime)) {
      sessionStorage.setItem('welcomeMusicPosition', String(audio.currentTime));
    }
  });
  window.addEventListener('pagehide', savePosition);
  window.addEventListener('beforeunload', savePosition);

  audio.addEventListener('loadedmetadata', () => {
    const savedPosition = Number(sessionStorage.getItem('welcomeMusicPosition') || 0);
    if (savedPosition > 0 && Number.isFinite(audio.duration)) {
      audio.currentTime = savedPosition % audio.duration;
    }
    if (shouldResumeMusic) startPlayback();
  }, { once: true });

  const scriptUrl = document.currentScript && document.currentScript.src
    ? document.currentScript.src
    : new URL('/static/js/welcome_music.js', window.location.href).href;
  audio.src = new URL(`../audio/${encodeURIComponent('Lola Amour - Fallen (Official Lyric Video).mp3')}`, scriptUrl).href;
  if (audio.readyState >= 1) audio.dispatchEvent(new Event('loadedmetadata'));

  if (shouldResumeMusic) state.textContent = 'Starting music';

  if (shouldResumeMusic) {
    const retryFromCustomerGesture = () => {
      if (audio.paused) startPlayback();
      window.removeEventListener('pointerdown', retryFromCustomerGesture);
      window.removeEventListener('keydown', retryFromCustomerGesture);
    };
    window.addEventListener('pointerdown', retryFromCustomerGesture, { once: true });
    window.addEventListener('keydown', retryFromCustomerGesture, { once: true });
  }
})();
