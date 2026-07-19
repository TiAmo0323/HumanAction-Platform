export function buildIntergenTextPayload(options) {
  const {
    text,
    numSamples,
    mode,
    retargetFeatureEnabled,
    targetCharacterId,
    mappingProfile,
    engine,
    strict
  } = options

  const payload = {
    text,
    num_samples: numSamples
  }

  const shouldRetarget = mode === 'cinematic' && Boolean(retargetFeatureEnabled)
  payload.retarget_enabled = shouldRetarget

  if (shouldRetarget) {
    payload.target_character_id = targetCharacterId
    payload.retarget_mapping_profile = mappingProfile
    payload.retarget_engine = engine
    payload.retarget_strict = strict
  }

  return payload
}
