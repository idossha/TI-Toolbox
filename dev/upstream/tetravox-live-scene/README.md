# Native scene API integration

TetraVox PR #44 provides a generic scene load/save API. Its `docs/SCENE_API.md` owns the wire contract;
`packages/app/src/main/scene-api-request.ts` and `src/shared/scene-api-protocol.ts` own its implementation.
The transport uses `--scene-request=<private JSON file>` and advertises `sceneApiProtocol: 1`.

TI's `desktop/src/main/nativeSceneBridge.ts` adapts this API. It chooses a destination under
`<project>/code/ti-toolbox/viewer/scenes/`, passes `expectedScenePath` to guard against another loaded
scene, and waits for the matching request ID and confirmed output path. These project conventions live
in TI, not TetraVox. Native TetraVox Save/Save As and application updating remain unchanged.

The earlier TI-specific protocol and native Save As redirection were superseded by the maintainer's
generic-API requirement. Tests in each repository cover the respective boundary; a native package
advertising the new capability is needed before TI can enable live saving.
