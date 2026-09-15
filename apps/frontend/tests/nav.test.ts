import { describe, expect, it } from 'vitest'
import type { LucideIcon } from 'lucide-react'
import { resolveActiveNavPath, type NavItem } from '@/lib/nav'

// icon 仅用于渲染，解析逻辑不依赖它
const item = (to: string): NavItem => ({
  to,
  label: to,
  icon: null as unknown as LucideIcon,
})

const NAV = [
  '/dashboard',
  '/catalog',
  '/submissions',
  '/submissions/pending',
  '/admin/settings',
].map(item)

describe('resolveActiveNavPath', () => {
  it('编辑工作台高亮自身，而不是「我的提交」（本轮修复的回归保护）', () => {
    // 该用例存在的原因：此前用裸 startsWith，/submissions/pending 会高亮
    // 第一个匹配项「我的提交」，与页面语义（编辑视角的审核队列）不符。
    expect(resolveActiveNavPath('/submissions/pending', NAV)).toBe(
      '/submissions/pending',
    )
  })

  it('「我的提交」页面自身仍正确高亮', () => {
    expect(resolveActiveNavPath('/submissions', NAV)).toBe('/submissions')
  })

  it('详情页归属其列表页', () => {
    expect(resolveActiveNavPath('/catalog/42', NAV)).toBe('/catalog')
  })

  it('未匹配的路径返回 undefined（不高亮任何项）', () => {
    expect(resolveActiveNavPath('/login', NAV)).toBeUndefined()
  })

  it('不会把相似前缀误判为父子（段级匹配）', () => {
    // /catalog-new 不是 /catalog 的子页面；裸 startsWith 会误匹配
    expect(resolveActiveNavPath('/catalog-new', NAV)).toBeUndefined()
  })

  it('空导航列表返回 undefined', () => {
    expect(resolveActiveNavPath('/dashboard', [])).toBeUndefined()
  })
})
