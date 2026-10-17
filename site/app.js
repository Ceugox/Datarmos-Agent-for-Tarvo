(function () {
  'use strict';
  var root = document.documentElement;
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var canObserve = 'IntersectionObserver' in window;
  if (!reduce && canObserve) root.classList.add('js');

  var brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  var num = function (v, dec) { return v.toLocaleString('pt-BR', { minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0 }); };

  // ---------- hero: arquivos entram, agente conecta, mês fecha ----------
  var stage = document.getElementById('stage');
  var steps = [['k1', 300], ['k2', 1300], ['k3', 3000], ['k4', 3700]];
  if (reduce || !canObserve) {
    steps.forEach(function (s) { stage.classList.add(s[0]); });
  } else {
    var timers = [];
    var play = function () {
      timers.forEach(clearTimeout); timers = [];
      stage.classList.remove('k1', 'k2', 'k3', 'k4');
      steps.forEach(function (s) { timers.push(setTimeout(function () { stage.classList.add(s[0]); }, s[1])); });
    };
    play();
    stage.addEventListener('click', play);
    stage.style.cursor = 'pointer';
    stage.title = 'Clique para rodar de novo';
  }

  // ---------- contadores ----------
  function countUp(el) {
    var target = parseFloat(el.dataset.count);
    var dec = el.dataset.money !== undefined ? 2 : (+el.dataset.dec || 0);
    var suffix = el.dataset.suffix || '';
    var fmt = function (v) { return el.dataset.money !== undefined ? brl.format(v) : num(v, dec) + suffix; };
    if (reduce) { el.textContent = fmt(target); return; }
    var t0 = null, dur = 1400;
    var tick = function (t) {
      if (!t0) t0 = t;
      var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 4);
      el.textContent = fmt(target * e);
      if (p < 1) requestAnimationFrame(tick); else el.textContent = fmt(target);
    };
    requestAnimationFrame(tick);
  }

  // ---------- revelação na rolagem ----------
  var seen = function (el) {
    el.classList.add('in');
    el.querySelectorAll('[data-count]').forEach(countUp);
    if (el.matches('[data-count]')) countUp(el);
  };
  var targets = document.querySelectorAll('.reveal, .timeline, .queue');
  if (canObserve) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { seen(e.target); io.unobserve(e.target); } });
    }, { threshold: 0.15, rootMargin: '0px 0px -8% 0px' });
    targets.forEach(function (el) { io.observe(el); });
  } else {
    targets.forEach(seen);
  }
  // contadores que não estão dentro de um .reveal (KPIs do hero)
  document.querySelectorAll('.hero [data-count]').forEach(countUp);

  // ---------- nav, progresso, brilho do fundo ----------
  var nav = document.querySelector('.nav');
  var bar = document.getElementById('progress');
  var links = [].slice.call(document.querySelectorAll('.nav nav a'));
  var secs = links.map(function (a) { return document.querySelector(a.getAttribute('href')); });
  var ticking = false;
  function onScroll() {
    var y = scrollY, h = document.body.scrollHeight - innerHeight;
    nav.classList.toggle('scrolled', y > 10);
    bar.style.setProperty('--p', h > 0 ? y / h : 0);
    root.style.setProperty('--gy', (y / Math.max(h, 1) * 100).toFixed(1) + '%');
    var cur = -1;
    secs.forEach(function (s, i) { if (s && s.getBoundingClientRect().top < innerHeight * 0.4) cur = i; });
    links.forEach(function (a, i) { a.classList.toggle('on', i === cur); });
    ticking = false;
  }
  addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  onScroll();

  // ---------- vídeo do YouTube ----------
  var cfg = window.SITE_CONFIG || {};
  if (cfg.repo) document.getElementById('repo-link').href = cfg.repo;
  function ytId(v) {
    if (!v) return '';
    v = String(v).trim();
    if (/^[\w-]{11}$/.test(v)) return v;
    var m = v.match(/(?:youtu\.be\/|v=|\/embed\/|\/shorts\/|\/live\/)([\w-]{11})/);
    return m ? m[1] : '';
  }
  var id = ytId(cfg.youtube);
  if (id) {
    var box = document.getElementById('video-box');
    box.innerHTML = '';
    var b = document.createElement('button');
    b.className = 'yt'; b.type = 'button'; b.setAttribute('aria-label', 'Assistir à apresentação em vídeo');
    b.style.backgroundImage = 'url(https://i.ytimg.com/vi/' + id + '/hqdefault.jpg)';
    b.innerHTML = '<span class="pulse" aria-hidden="true"><i></i></span>';
    b.addEventListener('click', function () {
      var f = document.createElement('iframe');
      f.src = 'https://www.youtube-nocookie.com/embed/' + id + '?autoplay=1&rel=0&modestbranding=1';
      f.title = 'Apresentação Datarmos'; f.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
      f.allowFullscreen = true; f.referrerPolicy = 'strict-origin-when-cross-origin';
      box.replaceChild(f, b);
    });
    box.appendChild(b);
  }

  // ---------- dashboard (Chart.js) ----------
  var R = window.RESULTS;
  function charts() {
    if (!window.Chart || !R) return;
    var C = window.Chart;
    C.defaults.color = 'rgba(243,245,251,.72)';
    C.defaults.font.family = '"JetBrains Mono", ui-monospace, monospace';
    C.defaults.font.size = 11.5;
    C.defaults.scale.ticks.maxRotation = 0;
    C.defaults.scale.ticks.autoSkipPadding = 12;
    C.defaults.borderColor = 'rgba(255,255,255,.08)';
    C.defaults.plugins.legend.labels.boxWidth = 10;
    C.defaults.plugins.legend.labels.boxHeight = 10;
    C.defaults.plugins.tooltip.backgroundColor = 'rgba(10,16,34,.95)';
    C.defaults.plugins.tooltip.borderColor = 'rgba(255,255,255,.16)';
    C.defaults.plugins.tooltip.borderWidth = 1;
    C.defaults.plugins.tooltip.padding = 10;
    C.defaults.animation = reduce ? false : { duration: 1200, easing: 'easeOutQuart' };
    var EMBER = '#ff8a50', GREEN = '#6ee7a8', AMBER = '#f5b84a', VIOLET = '#b9a3ff', BLUE = '#8fb3ff', MUTED = 'rgba(243,245,251,.28)';
    var money = function (v) { return brl.format(v); };
    var kfmt = function (v) { return Math.abs(v) >= 1000 ? 'R$ ' + num(v / 1000, 0) + ' mil' : 'R$ ' + num(v, 0); };
    var short = function (s) { return s.replace(/ (Ltda|Intercâmbio Ltda|Assessoria Educacional Ltda|Cursos Ltda|Cursos e Viagens Ltda|Exchange Ltda|de Idiomas Ltda)$/,'').replace(/^Escola /,''); };
    var made = {};
    function make(id, conf) {
      if (made[id]) return; made[id] = true;
      new C(document.getElementById(id), conf);
    }
    var builders = {
      'c-merchants': function () {
        var top = R.merchants.slice(0, 10);
        make('c-merchants', { type: 'bar', data: { labels: top.map(function (m) { return short(m.name); }), datasets: [
          { label: 'Checkout', data: top.map(function (m) { return m.checkout; }), backgroundColor: EMBER, borderRadius: 4, stack: 's' },
          { label: 'Remessa', data: top.map(function (m) { return m.remessa; }), backgroundColor: GREEN, borderRadius: 4, stack: 's' }] },
          options: { indexAxis: 'y', maintainAspectRatio: false, scales: { x: { stacked: true, ticks: { callback: kfmt } }, y: { stacked: true, grid: { display: false }, ticks: { font: { family: 'Onest', size: 13 }, color: '#f3f5fb' } } },
            plugins: { tooltip: { callbacks: { label: function (c) { return c.dataset.label + ': ' + money(c.raw); } } } } } });
      },
      'c-corrected': function () {
        var k = Object.keys(R.corrected);
        make('c-corrected', { type: 'bar', data: { labels: k.map(function (s) { return s.split(' · ')[0].replace('Casa do Estudante', 'Casa do Estudante').replace('Spreads negativos', 'Spread negativo'); }), datasets: [{ data: k.map(function (s) { return R.corrected[s]; }), backgroundColor: [GREEN, AMBER, EMBER, VIOLET], borderRadius: 6 }] },
          options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { title: function (c) { return k[c[0].dataIndex]; }, label: function (c) { return money(c.raw); } } } }, indexAxis: 'y', scales: { x: { ticks: { callback: kfmt, maxTicksLimit: 4, maxRotation: 0 } }, y: { grid: { display: false }, ticks: { font: { family: 'Onest', size: 12 }, color: '#f3f5fb' } } } } });
      },
      'c-coverage': function () {
        var lab = { INCLUIDO: 'Na comissão', CLASSIFICADO: 'Lançamento bancário', NAO_FATURAR: 'Não faturar (Atlas)', CONTESTAR: 'Contestar', REPETIDO: 'Repetido' };
        var k = Object.keys(R.coverage).sort(function (a, b) { return R.coverage[b] - R.coverage[a]; });
        make('c-coverage', { type: 'doughnut', data: { labels: k.map(function (s) { return lab[s] || s; }), datasets: [{ data: k.map(function (s) { return R.coverage[s]; }), backgroundColor: [GREEN, BLUE, AMBER, EMBER, VIOLET], borderColor: '#0a1022', borderWidth: 3 }] },
          options: { maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'right', labels: { font: { family: 'Onest', size: 12 } } }, tooltip: { callbacks: { label: function (c) { return c.label + ': ' + num(c.raw) + ' linhas'; } } } } } });
      },
      'c-late': function () {
        var L = R.late_adjustments;
        make('c-late', { type: 'bar', data: { labels: ['Comissão', 'Notas'], datasets: [
          { label: 'Antes do 06', data: [L.commission_before, L.notes_before], backgroundColor: MUTED, borderRadius: 6 },
          { label: 'Depois do 06', data: [L.commission_after, L.notes_after], backgroundColor: GREEN, borderRadius: 6 }] },
          options: { maintainAspectRatio: false, scales: { y: { min: 0, ticks: { callback: kfmt, maxTicksLimit: 5 } }, x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 0, font: { family: 'Onest', size: 12 } } } }, plugins: { tooltip: { callbacks: { label: function (c) { return c.dataset.label + ': ' + money(c.raw); } } } } } });
      },
      'c-div': function () {
        var d = R.divergences;
        make('c-div', { type: 'bar', data: { labels: d.map(function (x) { return x.name.replace('ORBE', 'Orbe').replace('PONTE', 'Ponte').replace(' Intercâmbio Ltda', '').replace(' (NOVA)', ''); }), datasets: [{ data: d.map(function (x) { return x.brl; }), backgroundColor: [EMBER, VIOLET, AMBER], borderRadius: 6 }] },
          options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (c) { return money(c.raw) + ' · ' + d[c.dataIndex].count + ' lançamentos'; } } } }, scales: { x: { ticks: { callback: kfmt, maxTicksLimit: 4, maxRotation: 0 } }, y: { grid: { display: false }, ticks: { font: { family: 'Onest', size: 12 }, color: '#f3f5fb' } } } } });
      },
      'c-pend': function () {
        var g = {};
        Object.keys(R.pending_by_owner).forEach(function (k) {
          var p = k.replace(' (financeiro)', '').split(' / ').sort(function (a, b) { return a === 'Helena' ? -1 : b === 'Helena' ? 1 : 0; }).join(' + ');
          g[p] = (g[p] || 0) + R.pending_by_owner[k];
        });
        var k = Object.keys(g).sort(function (a, b) { return g[b] - g[a]; });
        make('c-pend', { type: 'bar', data: { labels: k, datasets: [{ data: k.map(function (s) { return g[s]; }), backgroundColor: k.map(function (s) { return s === 'Helena' ? EMBER : s.indexOf('Helena') === 0 ? AMBER : BLUE; }), borderRadius: 6 }] },
          options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { stepSize: 2 } }, y: { grid: { display: false }, ticks: { font: { family: 'Onest', size: 12 }, color: '#f3f5fb' } } } } });
      },
      'c-time': function () {
        make('c-time', { type: 'bar', data: { labels: R.runtime_s.map(function (_, i) { return 'Execução ' + (i + 1); }), datasets: [{ data: R.runtime_s, backgroundColor: GREEN, borderRadius: 6 }] },
          options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (c) { return num(c.raw, 2) + ' s'; } } },
            subtitle: { display: true, text: 'Hoje: 8 dias úteis de conferência manual', color: EMBER, font: { size: 12 }, padding: { bottom: 8 } } },
            scales: { y: { min: 0, max: 0.6, ticks: { callback: function (v) { return num(v, 1) + ' s'; } } }, x: { grid: { display: false } } } } });
      }
    };
    var ids = Object.keys(builders);
    if (canObserve) {
      var cio = new IntersectionObserver(function (es) {
        es.forEach(function (e) { if (e.isIntersecting) { builders[e.target.id](); cio.unobserve(e.target); } });
      }, { threshold: 0.25 });
      ids.forEach(function (id) { cio.observe(document.getElementById(id)); });
    } else ids.forEach(function (id) { builders[id](); });
  }
  if (window.Chart) charts(); else addEventListener('load', charts);
})();
