// Single source of truth for document categories — used by the sidebar
// filter links and the upload form's tag chips. `value` is what's actually
// stored on Document.category and sent as ?category=; `label` is the
// sidebar's (slightly different) display text for it.
export const CATEGORIES: { value: string; label: string }[] = [
  { value: 'HR Policy', label: 'HR Policies' },
  { value: 'Benefits', label: 'Benefits' },
  { value: 'Contracts', label: 'Contracts' },
  { value: 'Onboarding', label: 'Onboarding' },
]
