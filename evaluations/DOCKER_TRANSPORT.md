# Step 28C: controlled Docker transport

Step 28D adds the reviewed offline functional worker on this unchanged transport;
see [FUNCTIONAL_WORKER.md](FUNCTIONAL_WORKER.md). Live model evaluation stays disabled.

Real transport is implemented for **trusted security probes only**. No Ollama
requests, host candidate execution, or live functional benchmarking are enabled.
DockerExecutionBackend.execute remains unconditionally blocked in this stage.

## Image and authorization

The user approved the official python:3.12.15-slim-bookworm Linux/amd64 image:

    python@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d

Registry-reported transfer: 47,558,478 bytes (45.4 MiB). Docker-reported image size:
197,098,586 bytes (188.0 MiB); physical WSL disk growth can differ. The standard
library covers all five tasks without additional packages. Reviewed metadata is
tracked in execution_image.json. The first pull ended with unexpected EOF; the
same approved digest succeeded on retry. The evaluator never automatically pulls.
[Official image](https://hub.docker.com/_/python).

## Enforced transport design

Docker CLI is called with argument arrays, shell=False, and desktop-linux context.
Only the local Docker Desktop Linux named pipe/standard Unix socket is allowed.
Preflight requires Linux/amd64, cgroup v2, CPU/memory/PID enforcement support,
built-in seccomp, the exact local immutable image and no image-declared volumes.

Every program gets a disposable random-name container: network none, numeric
UID/GID 65534:65534, read-only root, all capabilities dropped, no-new-privileges,
private namespaces, one CPU, one second CPU-time limit, 256 MiB memory/no extra
swap, 16 PIDs, 1 MiB /tmp and 1 MiB shared memory, bounded file sizes, no Docker
logging driver, no project/socket/credential/device mounts. Effective settings,
entrypoint and image environment are inspected before start. Model code cannot
provide Docker options, mounts, environment or entrypoint.

Programs are bounded UTF-8 bytes on stdin. Two readers share a 64 KiB stdout/stderr
cap during streaming, also bounding invalid UTF-8 replacement expansion. After a
two-second wall deadline, the CLI and container are killed; the owned container
is force-removed and independently inspected for absence. Cleanup runs on success,
nonzero exits and transport errors. Unconfirmed cleanup locks the transport.
Metadata/cleanup commands have separate ten-second deadlines outside program wall
time. A daemon outage may prevent removal; this fails closed, never claims success.
No Docker prune or unrelated container deletion is used.

Docker omits empty HostConfig.Mounts/Sysctls via omitempty. Only those optional
empty fields are normalized; nonempty values fail. Effective top-level Mounts
must still be present and empty; missing required limits fail closed.
[Moby schema](https://github.com/moby/moby/blob/master/api/types/container/hostconfig.go).

## Actual verification

Run explicitly (Docker must be running; the approved image must already exist):

    .venv\Scripts\python.exe -m evaluations.verify_docker_isolation

The command runs only repository-owned controlled programs, writes a timestamped
ignored report under evaluations/runs, and fails unless all mandatory checks pass.
run_security_checks() exposes the same explicit backend action. verify() is
read-only and never launches probes. Evidence is bound to daemon/image/policy and
transport/probe source hashes. Changed identities invalidate cached evidence.
Saved reports are never loaded as execution permits. execution_enabled stays false.

Final real run: **11/11 passed**, report isolation_20261020T155715302925Z.json:

| Probe | Actual behavior verified |
| --- | --- |
| normal_calculation | 42 returned as UID/GID 65534; actual cgroup and CPU-time limits read |
| wall_timeout | Sleeping process terminated at two-second deadline, killed/removed |
| network_denied | TCP ENETUNREACH, DNS failure, loopback only, no routes |
| host_files_denied | Harmless host sentinel absent via host aliases; zero mounts/socket; sentinel intact then removed |
| memory_limit | Allocation exceeded 256 MiB; OOMKilled, exit 137 before wall timeout |
| cpu_limit | One-CPU quota, RLIMIT_CPU=1; busy loop killed before wall timeout, without OOM |
| process_limit | 15 children plus parent; next fork EAGAIN, children reaped |
| readonly_nonroot | Root write and setuid(0) denied; bounded writable scratch; zero caps, NoNewPrivs=1, Seccomp=2; user-namespace creation denied |
| output_limit | Output flood truncated during streaming; cap respected, container removed |
| unsafe_configuration_rejected | Privileged/root/host-network/mount overrides rejected before Docker calls; ordinary real execution succeeds |
| cleanup | Success, nonzero-exit and timeout containers all removed with independent absence checks |

Reports retain effective inspection, stdout/stderr, exit/timeout/OOM status and
cleanup evidence. Runtime probes are separate from mocked unit tests. Final unit
regressions: **80/80 passed**, the original 64 plus 16 transport tests.

Initial real verification stopped all containers before execution due to wrongly
requiring omitted-empty fields; cleanup succeeded. The corrected schema handling
has regression coverage. A later preflight found Docker stopped after an internet
interruption and ran no probes; Docker was started before resuming. All failed,
blocked and superseded reports are retained, not counted as passing checks.

## Tests and limits of evidence

    .venv\Scripts\python.exe -m unittest -v test_agent test_evaluation_controller test_benchmark_reporting test_functional_evaluation test_execution_backend test_docker_transport

Transport unit tests cover unsafe flags, remote endpoints, missing resource/image
controls, policy mismatches before start, create/attach failures, cleanup failure,
timeouts, output/UTF-8 limits, stale identities and the closed live gate. They use
synthetic subprocess observations; no candidate Python runs on the host.

These behavior checks apply to the tested Docker/WSL/kernel/image combination.
They are not proof against kernel/container escapes, compromised Docker/images or
host administrators. DNS failure alone does not prove isolation; it is combined
with interface/route/TCP evidence. Syscall denial does not test every syscall.
The functional worker/harness and live enablement require another reviewed stage.
Interactive main.py, syntax evaluator, six-call budget and task fixtures are
unchanged. Generated reports and temporary artifacts are uncommitted.
