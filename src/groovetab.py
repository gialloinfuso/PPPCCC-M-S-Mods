#!/usr/bin/env python3
"""Groove-Tabellen aus grooves/grooves.json (Patch 08 groove; v1-Referenz der Tests).

parse(name) -> {'name', 'steps', 'off' (64 x Versatz in 1/256 Step), 'vel' (64 x Groove-Velocity)}; kuerzere Grooves sind
in der Datei schon auf 64 Steps wiederholt."""
import json
import pathlib

FILE = pathlib.Path(__file__).resolve().parents[1] / 'grooves' / 'grooves.json'


def parse(name):
    d = json.loads(FILE.read_text())
    g = next(x for x in d['grooves'] if x['name'] == name)
    return {'name': name, 'steps': g['steps'], 'off': list(g['offset_256th_step']), 'vel': list(g['velocity'])}
