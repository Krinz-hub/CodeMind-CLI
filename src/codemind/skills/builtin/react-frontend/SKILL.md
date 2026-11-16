---
name: react-frontend
version: 1.0.0
description: Modern React frontend architecture with functional components, hooks, type safety, and clean state boundaries.
category: frontend
triggers:
  manifests:
    - "package.json"
  globs:
    - "*.tsx"
    - "*.jsx"
  keywords:
    - "react"
    - "frontend"
    - "component"
    - "hook"
    - "props"
    - "state"
    - "jsx"
    - "tsx"
required_tools:
  - read_file
  - create_file
  - apply_patch
  - run_command
dependencies: []
conflicts:
  - vue-frontend
  - angular-frontend
workflow_steps:
  - "1. Inspect package.json to identify React version, build tooling (Vite, Next.js, CRA), and UI libraries."
  - "2. Define clear TypeScript interfaces for component props, emits, and state models."
  - "3. Implement functional components using standard React hooks (useState, useEffect, useMemo, useCallback)."
  - "4. Structure state lifting cleanly; separate presentation components from container/data-fetching components."
  - "5. Ensure accessible HTML semantics (ARIA labels, keyboard navigation, contrast)."
  - "6. Verify build and execute component tests (vitest, jest, or testing-library)."
constraints:
  - "Never mutate React state directly; always use state updater functions."
  - "Avoid useEffect for state synchronization that can be calculated during render."
  - "Do not introduce CSS-in-JS libraries if the project already standardizes on Tailwind CSS or CSS Modules."
verification:
  - "Run frontend test runner (npm test or npm run build) and confirm clean zero-error exit."
enabled: true
---

# React Frontend Engineering Workflow

## 1. Component Design Standards
- **Pure Functions:** Components should be idempotent render functions of their props and state.
- **Explicit Prop Contracts:** Declare exact TypeScript interfaces for props (`interface UserCardProps { ... }`).
- **Custom Hooks for Reusable Logic:** Extract non-visual stateful logic into dedicated `use*` custom hooks.

## 2. Execution Guidelines
1. Check `package.json` to verify whether TypeScript or JavaScript is standard for this workspace.
2. Locate component directory conventions (`src/components/`, `src/features/`, or `app/`).
3. Add component with minimal footprint and export cleanly via module index.
