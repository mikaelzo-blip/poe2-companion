# SUPERSEDED — DO NOT USE FOR IMPLEMENTATION

> **NOTICE**: This document contains early brainstormed concepts (such as an injected DirectX/Vulkan overlay and local SQLite cache) that conflict with the authoritative project architecture. It is preserved solely for historical context.
>
> **Authoritative Specification**: `POE2_Hermes_Companion_Blueprint_v2.md` and approved OpenSpec changes supersede all contents of this file. Do NOT use this file for design, implementation, or compliance reference.

---

### Historical Content (Superseded)

A desktop companion app for Path of Exile 2 providing real-time passive tree planning and overlay trade checks.

* Read game client logs to track active character state and zone progression.
* Display an in-game DirectX/Vulkan transparent overlay for quick item price evaluations.
* Parse local passive skill tree data offline to calculate character stat changes.
* Sync character build templates with community export formats via a local SQLite cache.
