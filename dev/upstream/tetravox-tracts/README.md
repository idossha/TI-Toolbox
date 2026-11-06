# Tractogram layers in the ViewSpec: the unapplied schema change

`tetravox-viewspec-v2.tracts.patch` is the additive change to `contracts/tetravox-viewspec-v2.schema.json`
that TetraVox's tractogram work (0.8.0, `tractLayerProtocol: 1`) asks of TI-Toolbox: dataset kind
`tractogram` with an optional `tract` block, `TractSampleSpec` and `TractsLayer`. `git apply --check` passed
against the schema on 2026-11-05. It is not applied because TI does not build tract layers yet; the work is in
[ROADMAP.md](../../../docs/dev/ROADMAP.md), the reasoning in [DECISIONS.md](../../../docs/dev/DECISIONS.md).

Apply it together with what uses it, and check `tractLayerProtocol` before sending a tractogram, as for
`sceneApiProtocol`: a copy without that field must never receive one. TetraVox's `docs/DECISIONS.md` owns the layer.
