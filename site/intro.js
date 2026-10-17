(function () {
  'use strict';

  var dialog = document.getElementById('video-intro');
  var video = document.getElementById('intro-video');
  var start = document.getElementById('start-intro');
  var skip = document.getElementById('skip-intro');
  var status = document.getElementById('intro-status');
  var brand = document.getElementById('intro-brand');
  var replay = document.querySelector('#video-box video');
  var replayBrand = document.getElementById('replay-brand');
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var closing = false;
  var outroTimer;

  function showBrand(element) {
    element.hidden = false;
    requestAnimationFrame(function () { element.classList.add('is-visible'); });
  }

  function showStart(error) {
    if (!dialog.open || closing) return;
    start.hidden = false;
    status.textContent = error && error.name === 'NotAllowedError'
      ? 'Toque para assistir com som ou pule para conhecer o site.'
      : 'Use o botão para reproduzir o vídeo ou pule para acessar o site.';
  }

  function play() {
    video.muted = false;
    video.volume = 1;
    if (video.error) video.load();
    video.play().catch(showStart);
  }

  function closeIntro() {
    if (!dialog.open || closing) return;
    closing = true;
    clearTimeout(outroTimer);
    video.pause();
    dialog.classList.add('is-closing');
    setTimeout(function () {
      dialog.close();
      var heading = document.getElementById('h-hero');
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }, reduce ? 0 : 180);
  }

  start.addEventListener('click', play);
  skip.addEventListener('click', closeIntro);
  video.addEventListener('playing', function () {
    start.hidden = true;
    status.textContent = 'Você pode pular a qualquer momento para conhecer a solução.';
  });
  video.addEventListener('error', showStart);
  video.addEventListener('ended', function () {
    start.hidden = true;
    showBrand(brand);
    status.textContent = 'Datarmos. Conheça a solução a seguir.';
    outroTimer = setTimeout(closeIntro, reduce ? 1000 : 2200);
  });
  replay.addEventListener('ended', function () {
    showBrand(replayBrand);
    setTimeout(function () {
      replayBrand.hidden = true;
      replayBrand.classList.remove('is-visible');
    }, reduce ? 1000 : 2200);
  });
  replay.addEventListener('play', function () {
    replayBrand.hidden = true;
    replayBrand.classList.remove('is-visible');
  });
  dialog.addEventListener('cancel', function (event) {
    event.preventDefault();
    closeIntro();
  });
  dialog.addEventListener('close', function () { video.pause(); });

  dialog.showModal();
  play();
})();
