import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import { authGuard } from './guards'

// Each module in `routes/` default-exports its routes, so a new view adds a file
// instead of editing a shared one (and avoids conflicts between pull requests).
const modules = import.meta.glob<{ default: RouteRecordRaw[] }>('./routes/*.ts', { eager: true })

/** Every route of the application, gathered from `routes/*.ts`. */
export const routes: RouteRecordRaw[] = Object.values(modules).flatMap((m) => m.default)

export const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(authGuard)
