// kin: follow a member's state, or a hub's word for a member, from a page.
//
// The stream first: GET <events> is server-sent events, and every `state`
// event is the snapshot, so a cue reaches the page as soon as it lands. While
// the stream is down -- an old host, a proxy that buffers, a restart -- the
// page asks GET <state> every `poll` ms instead, and stops asking the moment
// the stream is back. Either way the page is handed snapshots, never told
// which path brought one.
//
// A classic script, so a page with no bundler loads it with a <script> tag
// and a bundled page imports it for its effect; both call kin.follow.
//
//   const stop = kin.follow({events: '/family/events', state: '/family/state'},
//                           snapshot => draw(snapshot),
//                           {onLink: link => badge(link)});  // 'stream' | 'polling' | 'down'
(function (root) {
    'use strict';

    function follow(urls, onSnapshot, options) {
        const poll = (options && options.poll) || 1000;
        const onLink = (options && options.onLink) || function () {};
        let source = null;
        let timer = null;
        let stopped = false;
        let link = null;

        function say(next) {
            if (next !== link) { link = next; onLink(next); }
        }

        function polling() {
            if (timer !== null || stopped) return;
            const ask = () => {
                fetch(urls.state, {cache: 'no-store'})
                    .then(r => r.ok ? r.json() : Promise.reject(r.status))
                    .then(snapshot => { if (!stopped && link !== 'stream') { say('polling'); onSnapshot(snapshot); } })
                    .catch(() => { if (link !== 'stream') say('down'); })
                    .finally(() => { if (timer !== null) timer = setTimeout(ask, poll); });
            };
            timer = setTimeout(ask, 0);
        }

        function quiet() {
            if (timer !== null) { clearTimeout(timer); timer = null; }
        }

        if (typeof EventSource === 'function' && urls.events) {
            source = new EventSource(urls.events);
            source.addEventListener('state', event => {
                quiet();
                say('stream');
                onSnapshot(JSON.parse(event.data));
            });
            // EventSource reconnects by itself; until it does, poll.
            source.onerror = () => { if (!stopped) { say('down'); polling(); } };
        } else {
            polling();
        }

        return function stop() {
            stopped = true;
            quiet();
            if (source) source.close();
        };
    }

    root.kin = Object.assign(root.kin || {}, {follow: follow});
})(typeof globalThis !== 'undefined' ? globalThis : window);
