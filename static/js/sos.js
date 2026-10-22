/* SOS confirm flow (Step 2.3).
 *
 * Geolocation is requested only after the user presses "Confirm and send"
 * inside the modal. If location is denied, unavailable or times out, the form
 * is submitted with location_source=simulated and the server uses a labelled
 * demo location.
 */
(function () {
  'use strict';

  var form = document.getElementById('sos-form');
  var modalEl = document.getElementById('sosModal');
  if (!form || !modalEl) { return; }

  var confirmBtn = document.getElementById('sos-confirm');
  var statusEl = document.getElementById('sos-status');
  var sourceField = document.getElementById('sos-location-source');
  var latField = document.getElementById('sos-latitude');
  var lngField = document.getElementById('sos-longitude');

  var LOCATION_TIMEOUT_MS = 8000;
  var attempt = 0;      // bumped on every confirm and on every modal close
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

  confirmBtn.addEventListener('click', function (event) {
    event.preventDefault();
    if (sending) { return; }

    attempt += 1;
    var mine = attempt;
    function current() { return mine === attempt; }

    confirmBtn.disabled = true;

    function useSimulated(reason) {
      if (!current()) { return; }
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
        if (!current()) { return; }
        setStatus('Location found. Sending your request...');
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

  // Closing the modal (Cancel, X, Esc) cancels any pending location request.
  modalEl.addEventListener('hidden.bs.modal', function () {
    if (sending) { return; }
    attempt += 1;
    confirmBtn.disabled = false;
    setStatus('');
  });
})();