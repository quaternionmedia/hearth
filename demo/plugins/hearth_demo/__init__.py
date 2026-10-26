"""Loopback, the demo's show, and the members it hosts in the hub.

``members`` says what each hosted member is: a metronome of the hub's family,
a rack of another, and the stagehand, which does the show's acts backstage.
``backstage`` keeps the show's other members running, makes the show, and
runs the checks. Neither imports anything of ShowRunner. ``show`` and
``hosted`` make them ShowRunner plugins, and are imported only by a hub
loading its plugins through the ``showrunner`` entry points.
"""
