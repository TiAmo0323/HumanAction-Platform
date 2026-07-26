export function buildIntergenSkinPayload(text, personSkinIds, options) {
  const [personASkinId, personBSkinId] = personSkinIds
  const optionById = new Map(options.map((option) => [option.id, option]))
  const personOptions = [optionById.get(personASkinId), optionById.get(personBSkinId)]

  if (!String(text || '').trim()) throw new Error('Text prompt is required')
  if (personOptions.some((option) => !option || option.outputKind !== 'retarget')) {
    throw new Error('Both InterGen persons must use registered retarget skins')
  }

  const skinIds = [...new Set([personASkinId, personBSkinId])]
  return {
    text,
    person_a_skin_id: personASkinId,
    person_b_skin_id: personBSkinId,
    skin_ids: skinIds,
    skin_id: personASkinId,
    retarget_enabled: true
  }
}
