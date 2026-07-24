export const DEFAULT_SKIN_ID = 'smpl'

export const skinOptions = Object.freeze([
  Object.freeze({
    id: 'smpl',
    label: 'SMPL',
    category: '基础人体模型',
    description: '查看标准 SMPL / SMPL-X 人体网格动画',
    outputKind: 'smpl',
    backendMode: 'smplx'
  }),
  Object.freeze({
    id: 'robot',
    label: '机器人',
    category: '角色蒙皮',
    description: '查看经过 Blender / Rokoko 重定向的机器人动画',
    outputKind: 'retarget',
    backendMode: 'smplx'
  })
])

export function getSkinOption(skinId, options = skinOptions) {
  return options.find((option) => option.id === skinId) || options[0] || skinOptions[0]
}
