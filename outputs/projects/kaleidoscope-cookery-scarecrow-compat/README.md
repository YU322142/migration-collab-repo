# Kaleidoscope Cookery Scarecrow compatibility

Candidate13's 1.21.11 source writes `HandItems`/`ArmorItems` as lists of
slotted stacks. The 1.21.1 NeoForge backport expects `ItemStackHandler`
compounds. The mixin converts only legacy list tags at the start of the target
loader, preserving every stack and explicit slot. Target-format compounds,
absent fields, and unrelated tag types are left untouched, so the operation is
idempotent and the next normal world save naturally persists the target form.

