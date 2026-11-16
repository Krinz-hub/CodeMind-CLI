---
name: react-native-expo
version: 1.0.0
description: Cross-platform mobile application development using React Native and the Expo SDK.
category: mobile
triggers:
  manifests:
    - "app.json"
    - "package.json"
  globs:
    - "*.native.tsx"
    - "*.native.ts"
  keywords:
    - "expo"
    - "react-native"
    - "mobile"
    - "ios"
    - "android"
    - "navigation"
    - "screen"
required_tools:
  - read_file
  - create_file
  - apply_patch
  - run_command
dependencies:
  - react-frontend
conflicts: []
workflow_steps:
  - "1. Inspect app.json and package.json to identify Expo SDK version, plugins, and navigation structure."
  - "2. Design mobile screens respecting device safe areas, status bars, and notch insets."
  - "3. Use core React Native primitives (View, Text, ScrollView, FlatList, Pressable) rather than web DOM tags (div, span)."
  - "4. Ensure touch interactions provide immediate visual feedback (Pressable with active opacity/ripple)."
  - "5. Verify responsive layout across phone and tablet aspect ratios with StyleSheet or nativewind."
constraints:
  - "Never use web DOM elements (<div>, <p>, <a>) in React Native code."
  - "Always import core layout components from 'react-native' or 'react-native-safe-area-context'."
  - "Avoid inline object creation inside render methods for FlatList items; use memoized renderItem callbacks."
verification:
  - "Run typescript check (npx tsc --noEmit) and linting checks without error."
enabled: true
---

# React Native & Expo Engineering Workflow

## 1. Core Principles
- **Native Primitives:** Mobile platforms do not have a DOM. Always utilize `View`, `Text`, `Image`, `TextInput`, and `Pressable`.
- **Safe Area Insets:** Wrap top-level screen containers in `SafeAreaProvider` and `SafeAreaView` from `react-native-safe-area-context`.
- **Navigation Conventions:** Follow Expo Router filesystem-based conventions (`app/(tabs)/`) or React Navigation stack patterns depending on project structure.
