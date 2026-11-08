/* Shows the newest ZestBay release tag from GitHub in the page's version
   spots (the hero pill and the footer). Nothing is hardcoded: until a tag is
   known the version text stays hidden, so JavaScript being off, GitHub being
   unreachable or the rate limit being hit just means no version is shown.

   The unauthenticated GitHub API allows 60 requests an hour per IP, so the
   answer is cached in localStorage for an hour. Only plain vX.Y.Z tags count
   (pre-releases such as v1.3.0-rc1 are ignored). */
(function () {
  "use strict";

  var API = "https://api.github.com/repos/lemonxah/zestbay/tags?per_page=100";
  var KEY = "zestbay:latest-tag";
  var TTL = 60 * 60 * 1000;

  function parse(name) {
    var m = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(name || "");
    return m ? [+m[1], +m[2], +m[3]] : null;
  }

  function newer(a, b) {
    for (var i = 0; i < 3; i++) {
      if (a[i] !== b[i]) return a[i] > b[i];
    }
    return false;
  }

  // The highest vX.Y.Z among the tags, as "X.Y.Z", or null.
  function latest(tags) {
    var best = null;
    for (var i = 0; i < tags.length; i++) {
      var v = parse(tags[i] && tags[i].name);
      if (v && (!best || newer(v, best))) best = v;
    }
    return best ? best.join(".") : null;
  }

  function show(version) {
    var spots = document.querySelectorAll("[data-version]");
    for (var i = 0; i < spots.length; i++) spots[i].textContent = "v" + version;
    var wrappers = document.querySelectorAll(".ver");
    for (var j = 0; j < wrappers.length; j++) wrappers[j].hidden = false;
  }

  function cached() {
    try {
      var c = JSON.parse(localStorage.getItem(KEY));
      if (c && c.version && Date.now() - c.at < TTL) return c.version;
    } catch (e) { /* storage blocked or unreadable: fetch instead */ }
    return null;
  }

  function remember(version) {
    try {
      localStorage.setItem(KEY, JSON.stringify({ version: version, at: Date.now() }));
    } catch (e) { /* storage blocked: just fetch again next time */ }
  }

  var hit = cached();
  if (hit) {
    show(hit);
    return;
  }

  fetch(API, { headers: { Accept: "application/vnd.github+json" } })
    .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
    .then(function (tags) {
      var version = latest(tags);
      if (version) {
        remember(version);
        show(version);
      }
    })
    .catch(function () { /* leave the version hidden */ });
})();
