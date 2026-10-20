"""Checking for a new Rialto, only when a person asks.

Adapted from We The Indies' update check, minus the
download-and-apply half: this version of Rialto only *checks*, then opens the
release page in the browser. Manual, stateless, one sentence back. Nothing
here runs unless Help > Check for a New Rialto is clicked, and a failed
check never touches a build or anything Rialto writes onto a disc or
into a player's install.

Standard library only, Python 3.9 upward, so the first-run bootstrap does
not grow a dependency.
"""
