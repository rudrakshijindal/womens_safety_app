
(function () {
  'use strict';

  var LOCATION_TIMEOUT_MS = 8000;

  function initStartForm() {
    var form = document.getElementById('journey-form');
    if (!form) { return; }

    var button = document.getElementById('journey-start-button');
    var statusEl = document.getElementById('journey-status');
    var sourceField = document.getElementById('journey-location-source');
    var latField = document.getElementById('journey-latitude');
    var lngField = document.getElementById('journey-longitude');
    var sending = false;

    function setStatus(text) { statusEl.textContent = text; }

    function send(source, lat, lng) {
      if (sending) { return; }
      sending = true;
      sourceField.value = source;
      latField.value = (lat === undefined) ? '' : String(lat);
      lngField.value = (lng === undefined) ? '' : String(lng);
      form.submit();
    }

    // The browser validates required/maxlength first; this runs only if valid.
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      if (sending) { return; }
      button.disabled = true;

      function useSimulated(reason) {
        setStatus(reason + ' Using a simulated demo location.');
        send('simulated');
      }

      if (!('geolocation' in navigator)) {
        useSimulated('Location is not available in this browser.');
        return;
      }

      setStatus('Asking your browser for your location...');
      navigator.geolocation.getCurrentPosition(
        function (position) {
          setStatus('Location found. Starting your journey...');
          send(
            'device',
            position.coords.latitude.toFixed(6),
            position.coords.longitude.toFixed(6)
          );
        },
        function (error) {
          if (error && error.code === 1) {
            useSimulated('Location permission was denied.');
          } else {
            useSimulated('Your location could not be read.');
          }
        },
        { enableHighAccuracy: true, timeout: LOCATION_TIMEOUT_MS, maximumAge: 0 }
      );
    });

    // Coming back with the browser Back button: make the form usable again.
    window.addEventListener('pageshow', function (event) {
      if (event.persisted) {
        sending = false;
        button.disabled = false;
        setStatus('');
      }
    });
  }

  function initMap() {
    var el = document.getElementById('journey-map');
    if (!el) { return; }

    if (typeof L === 'undefined') {
      el.textContent = 'The map could not be loaded. It needs an internet connection.';
      return;
    }

    var lat = parseFloat(el.getAttribute('data-lat'));
    var lng = parseFloat(el.getAttribute('data-lng'));
    var hasStart = isFinite(lat) && isFinite(lng);

    var map = L.map(el, { scrollWheelZoom: false });
    map.setView(hasStart ? [lat, lng] : [22.5, 79.0], hasStart ? 15 : 4);

    L.tileLayer(el.getAttribute('data-tiles'), {
      maxZoom: 19,
      attribution: el.getAttribute('data-attribution')
    }).addTo(map);

    if (hasStart) {
      var label = document.createElement('span');
      label.textContent = el.getAttribute('data-start-label') || 'Start location';
      L.circleMarker([lat, lng], {
        radius: 9, color: '#751e3b', fillColor: '#8c2748', fillOpacity: 0.9, weight: 2
      }).addTo(map).bindPopup(label);
    }

    var startBtn = document.getElementById('live-start');
    var stopBtn = document.getElementById('live-stop');
    var liveStatus = document.getElementById('live-status');
    if (!startBtn || !stopBtn) { return; }   // completed journeys have no live controls

    var watchId = null;
    var liveMarker = null;
    var accuracyCircle = null;
    var firstFix = true;

    function setLive(text) { if (liveStatus) { liveStatus.textContent = text; } }

    function stopWatch(message) {
      if (watchId !== null) {
        navigator.geolocation.clearWatch(watchId);
        watchId = null;
      }
      if (liveMarker) { map.removeLayer(liveMarker); liveMarker = null; }
      if (accuracyCircle) { map.removeLayer(accuracyCircle); accuracyCircle = null; }
      firstFix = true;
      startBtn.hidden = false;
      stopBtn.hidden = true;
      if (message) { setLive(message); }
    }

    function onPosition(position) {
      var latlng = [position.coords.latitude, position.coords.longitude];
      var accuracy = position.coords.accuracy || 0;
      if (!liveMarker) {
        liveMarker = L.circleMarker(latlng, {
          radius: 8, color: '#0b57d0', fillColor: '#0b57d0', fillOpacity: 0.9, weight: 2
        }).addTo(map);
        accuracyCircle = L.circle(latlng, {
          radius: accuracy, color: '#0b57d0', weight: 1, fillOpacity: 0.08
        }).addTo(map);
      } else {
        liveMarker.setLatLng(latlng);
        accuracyCircle.setLatLng(latlng);
        accuracyCircle.setRadius(accuracy);
      }
      if (firstFix) { map.setView(latlng, 16); firstFix = false; } else { map.panTo(latlng); }
      setLive(
        'Live location updated at ' + new Date().toLocaleTimeString() +
        '. Shown on this page only; not saved or shared.'
      );
    }

    function onError(error) {
      if (error && error.code === 1) {
        stopWatch('Location permission was denied. The map keeps showing the start location.');
      } else {
        setLive('Your location could not be read right now. Still trying...');
      }
    }

    startBtn.addEventListener('click', function () {
      if (!('geolocation' in navigator)) {
        setLive('Location is not available in this browser.');
        return;
      }
      startBtn.hidden = true;
      stopBtn.hidden = false;
      setLive('Asking your browser for your location...');
      watchId = navigator.geolocation.watchPosition(onPosition, onError, {
        enableHighAccuracy: true, maximumAge: 10000, timeout: 15000
      });
    });

    stopBtn.addEventListener('click', function () {
      stopWatch('Live location stopped. The map shows the start location again.');
    });

    window.addEventListener('pagehide', function () { stopWatch(); });
  }

  initStartForm();
  initMap();
})();