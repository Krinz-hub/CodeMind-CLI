---
name: ui-ux-design
version: 1.0.0
description: User interface hierarchy, visual balance, responsive breakpoints, feedback states, and accessibility standards.
category: design
triggers:
  manifests:
    - "tailwind.config.js"
    - "tailwind.config.ts"
  globs:
    - "*.css"
    - "*.scss"
  keywords:
    - "ui"
    - "ux"
    - "design"
    - "styling"
    - "css"
    - "tailwind"
    - "responsive"
    - "accessibility"
    - "color"
    - "layout"
    - "theme"
required_tools:
  - read_file
  - create_file
  - apply_patch
dependencies: []
conflicts: []
workflow_steps:
  - "1. Inspect existing styling systems (Tailwind CSS, CSS Modules, Styled Components, vanilla CSS) and design tokens."
  - "2. Establish visual hierarchy: primary focal points, secondary actions, and muted tertiary metadata."
  - "3. Implement complete interaction states: default, hover, active, focus-visible, disabled, and loading skeletons."
  - "4. Ensure responsive behavior across mobile (375px), tablet (768px), and desktop (1280px+) viewports."
  - "5. Verify accessibility: WCAG AA color contrast (minimum 4.5:1 for normal text), keyboard focus rings, and screen-reader labels."
constraints:
  - "Never remove focus outlines (`outline: none`) without providing an explicit, high-contrast replacement."
  - "Do not introduce arbitrary hardcoded hex color codes when the project defines a standardized design token palette."
  - "Ensure touch targets on interactive elements meet minimum 44x44px standards."
verification:
  - "Verify semantic HTML structure and CSS syntax without layout shift or styling regression."
enabled: true
---

# UI/UX Design & Styling Guidelines

## 1. Visual Hierarchy & Spacing
- **Consistent Spacing Scale:** Use standard 4px/8px multiples (e.g. 4px, 8px, 12px, 16px, 24px, 32px, 48px).
- **Typography Scale:** Differentiate headlines, subheads, body copy, and metadata clearly using font weight and scale.
- **State Completeness:** Every interactive component must handle:
  - *Idle / Default*
  - *Hover / Pointer-over*
  - *Focus / Keyboard navigation*
  - *Loading / Busy state*
  - *Disabled state*
  - *Error / Validation failed state*
