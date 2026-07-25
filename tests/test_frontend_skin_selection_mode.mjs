import assert from 'node:assert/strict'
import {
  MULTI_SKIN_SELECTION,
  SINGLE_SKIN_SELECTION,
  normalizeSkinSelection,
  toggleSkinSelection
} from '../project/src/config/skinSelection.js'

assert.deepEqual(
  toggleSkinSelection(['smpl'], 'robot', SINGLE_SKIN_SELECTION),
  ['robot'],
  'single-select must replace the default SMPL selection'
)
assert.deepEqual(
  toggleSkinSelection(['robot'], 'robot', SINGLE_SKIN_SELECTION),
  ['robot'],
  'single-select must never clear the only selected skin'
)
assert.deepEqual(
  toggleSkinSelection(['smpl'], 'robot', MULTI_SKIN_SELECTION),
  ['smpl', 'robot'],
  'multi-select must append a newly selected skin'
)
assert.deepEqual(
  toggleSkinSelection(['smpl', 'robot'], 'smpl', MULTI_SKIN_SELECTION),
  ['robot'],
  'multi-select must allow removing one of multiple skins'
)
assert.deepEqual(
  toggleSkinSelection(['robot'], 'robot', MULTI_SKIN_SELECTION),
  ['robot'],
  'multi-select must retain at least one skin'
)
assert.deepEqual(
  normalizeSkinSelection(['smpl', 'robot'], SINGLE_SKIN_SELECTION),
  ['robot'],
  'returning to single-select must retain the most recently added skin'
)
assert.deepEqual(
  normalizeSkinSelection(['smpl', 'robot'], MULTI_SKIN_SELECTION),
  ['smpl', 'robot'],
  'switching to multi-select must preserve the current selection'
)
assert.deepEqual(
  toggleSkinSelection(['robot'], 'future-skin', MULTI_SKIN_SELECTION),
  ['robot', 'future-skin'],
  'selection logic must remain data-driven for future skins'
)

console.log(JSON.stringify({
  default_mode: SINGLE_SKIN_SELECTION,
  single_robot_click: ['robot'],
  multi_robot_click: ['smpl', 'robot'],
  multi_to_single_keeps_latest: ['robot'],
  future_skin_supported: true
}, null, 2))
