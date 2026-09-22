# mco API contract

This document states what `mco` promises to keep stable while MARCO's internals
and model format change, and how a new runtime plugs in.

## Layers

```
user code ──► mco (public API)          load · compile · inspect · benchmark
                │                       Model · Session · Result · Status · Evidence · Trace
                ▼
             mco.backends (contract)    Backend · BackendModel · BackendSession
                │
       ┌────────┴──────────┐
       ▼                   ▼
 marco-kgpack          mco-native
 (MARCO engine,        (placeholder until the MCO Format 1
  .kgpack payload)      runtime exists)
```

* Only `mco/backends/marco.py` imports MARCO modules. A test enforces this, and
  another checks that `import mco` followed by `mco.inspect()` imports no MARCO
  module at all.
* MARCO's verdict labels (`인정`, `미지`, `B2`, ...) and trace keys are mapped to
  `Status`, `Evidence` and `TraceStep` inside that one file. When MARCO changes a
  label, only that file changes.

## Stability rules (API version 1)

Stable:

* The names exported from `mco` (`mco.__all__`) and their signatures. Parameters
  may be added, as keyword-only with defaults, but never removed or reordered.
* `Result.answer`, `status`, `evidence`, `trace`, `input`, `backend`, `ok`, and
  `to_dict()` keys.
* `Status` values. New values may be added later, so treat an unrecognised
  status like `unknown`.
* `Evidence.kind`, `text`, `source`, `score`, and `TraceStep.stage`, `summary`.
  New kinds and stages may appear.
* `Capability` names, and the `ModelInfo` fields other than `manifest`.
* The error class hierarchy.
* CLI subcommands, flags and exit codes.

Not stable (backend-specific; use only for debugging):

* `Result.raw_status`, `Result.raw`
* `Evidence.detail`, `TraceStep.detail`
* `ModelInfo.manifest`

Current evidence kinds: `graph_node`, `graph_path`, `state_transition`,
`derived_fact`, `definition`, `fact`, `external_source`. Current trace stages:
`understand`, `route`, `judge`, `reason`, `retrieval`, `research`, `plan`,
`verify`, `fact`.

## Sessions and isolation

* `Model.run` uses one default session per model.
* `Model.session()` returns an independent session. With the MARCO backend, each
  session owns a separate MARCO application object, because MARCO keeps some
  dialogue state per application. When a session is closed, its application is
  reset and reused, since opening one re-indexes the pack.
* `Model.reason()` always starts from a clean context, and leaves both the
  default session and the other sessions untouched.

## MARCO backend options

| Option | Default | Meaning |
|---|---|---|
| `allow_network` | `False` | Let MARCO research unknown questions on the web and propose learning plans. When off, those questions come back as `unknown` |
| `overlay_dir` | temporary directory | Where learned knowledge is stored. The model file itself is never modified |
| `marco_root` | discovery | The MARCO checkout to run |

## `.mco` compatibility container (container version 0)

A ZIP with exactly two members, written with fixed timestamps so that the
output is byte-deterministic:

* `mco.json`:
  ```json
  {"format": "mco", "container": "compat-zip", "container_version": 0, "api": 1,
   "name": "MARCO-1", "build_id": "sha256-<12 hex>", "generator": "mco 0.1.0",
   "payload": {"kind": "kgpack", "path": "payload.kgpack", "bytes": 0, "sha256": "…",
               "kgpack_version": 3},
   "runtime": {"backend": "marco-kgpack"},
   "model": {"...": "the kgpack's model declaration (language, axioms)"}}
  ```
* `payload.kgpack`: the unmodified MARCO pack.

Loading verifies the payload hash and every file hash inside the pack. Unknown
container versions are rejected, not guessed at. Native files start with the
provisional magic `\x89MCO` and go to the `mco-native` backend.

## Writing a backend

```python
from mco.backends import Backend, BackendModel, BackendSession, register_backend
import mco

class MySession(BackendSession):
    def run(self, text: str) -> mco.Result: ...
    def reset(self) -> None: ...

class MyModel(BackendModel):
    def __init__(self, info: mco.ModelInfo): self.info = info
    def new_session(self) -> BackendSession: return MySession()
    # reason() has a default: feed text facts, then ask the question.
    # Override it to accept structured facts natively.

@register_backend
class MyBackend(Backend):
    name = "my-runtime"
    formats = ("mco-native",)       # ModelFile.kind values it opens
    priority = 20
    def describe(self, file) -> mco.ModelInfo: ...
    def open(self, file, options) -> BackendModel: return MyModel(self.describe(file))
```

A backend can also be published as a plugin through the `mco.backends` entry
point group:

```toml
[project.entry-points."mco.backends"]
my-runtime = "my_package.backend:MyBackend"
```

How a backend is chosen: `load(..., backend=name)` if given. Otherwise the
backend recorded in the file's manifest, and failing that, the
highest-priority backend that accepts the file's format.
