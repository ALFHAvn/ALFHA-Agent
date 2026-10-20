# Step 28: execution prerequisites and fail-closed backend interface

Historical Step 28 findings follow. WSL 2 and Docker became operational in Step
28B. See [DOCKER_TRANSPORT.md](DOCKER_TRANSPORT.md) for Step 28C's real controlled
transport and verification results. Live model execution remains disabled.

## Actual status

The production Docker adapter is a **disabled interface**, not a working secure
executor. No container execution transport is enabled. Runtime security probes and
the live functional benchmark have **not run**. This follows the requested fallback
when system prerequisites are unavailable; mocked tests do not establish security.

Read-only checks on this host found:

| Item | Observed result |
| --- | --- |
| OS | Microsoft Windows 11 Home Single Language, build 26200 |
| RAM | About 16 GiB |
| HypervisorPresent | True |
| CPU virtualization/SLAT flags | False in CIM while hypervisor is active; inconclusive |
| WSL | wsl --status reports not installed |
| Docker/Podman | Neither executable found on PATH |
| Optional-feature state | Administrator elevation required; not established |

The hypervisor result does not prove WSL 2 is configured. No BIOS, Windows feature,
security setting, privileged software or image installation was changed.

## Recommended runtime and manual installation

Use Docker Desktop with the WSL 2 backend and **Linux containers**. Consult the
current [Docker Windows installation guide](https://docs.docker.com/desktop/setup/install/windows-install/)
for supported OS/WSL versions and hardware requirements. Windows Home supports
Linux containers; a Windows-container backend is unsuitable for this design.

The following are manual instructions, **not commands executed by ALFHA/Codex**.
System installation and feature changes require the user's explicit approval.

1. In an administrator PowerShell, inspect feature state if needed:

       Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
       Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux

2. Once installation is approved, follow Microsoft's
   [WSL installation instructions](https://learn.microsoft.com/en-us/windows/wsl/install).
   Installing WSL without an ordinary distribution is supported:

       wsl --install --no-distribution

   Reboot when prompted. Then update/check WSL:

       wsl --update
       wsl --version
       wsl --status

   See Microsoft's [command reference](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)
   for --no-distribution. Do not change BIOS/security settings automatically if
   prerequisites still fail; inspect the diagnostics first.

3. Download/install Docker Desktop using its official guide. Choose the WSL 2
   engine and Linux containers. Leave project folders/credentials unshared and do
   not expose the daemon over an unauthenticated TCP endpoint.

4. Verify the client/server are available and the server reports linux:

       docker version
       docker info --format '{{.OSType}}'

5. After approval for the image download, select an official Python Linux image
   and record its immutable repository digest. Example manual preparation:

       docker pull python:3.12-slim
       docker image inspect python:3.12-slim --format '{{index .RepoDigests 0}}'

   The evaluator accepts only python@sha256: followed by 64 lowercase hexadecimal
   characters. It does not pull images. A digest is an identity requirement, not
   proof of trust or isolation. Future code must verify the actual Linux image ID,
   image configuration, local daemon identity and effective container settings.

Installing these prerequisites **does not enable execution in this revision**.
The real transport and security probes must be implemented and validated first.

## Implemented interface and integration

execution_backend.py provides:

- ExecutionBackend.verify/execute interface and DockerExecutionBackend adapter.
- A fixed, immutable proposed policy and a conservative docker-inspect validator.
- Structured blocked results with stdout, stderr, exit status, timeout and cleanup
  fields; all outputs are empty/null when execution never starts.
- An explicit not_run status for every required runtime security probe.
- An evaluator integration seam that requires complete verification evidence,
  checks static policy, grades returned values/types on the host, checks unchanged
  inputs/new-list identity, and refuses successful grading after timeout, output,
  exit-status or cleanup failures. Dependency-injected adapters are trusted test
  doubles only; the CLI uses only the disabled production adapter.

The existing five task definitions, 29 vectors and tool telemetry are unchanged.
Functional pass/fail remains separate from syntax and model tool-use outcomes.
The model still receives six tool calls; verification/backend work adds none.
The interactive agent and syntax evaluator are unchanged.

Record the current blocked state:

    .venv\Scripts\python.exe -m evaluations.evaluate_functional --verify-execution

This writes a fresh ignored functional_static report and exits 2. Each probe is
not_run with no evidence. --live is also blocked before any model request. There
is no flag, saved JSON token or installed-tool check that can enable the adapter.

## Proposed controls: not currently enforced

| Control | Fixed plan |
| --- | --- |
| Network | none; no host networking, published ports or extra hosts |
| User | Numeric UID/GID 65534:65534 |
| Privileges | Non-privileged; all capabilities dropped; no-new-privileges; default seccomp required |
| Filesystem | Read-only root; no bind mounts, volumes, host paths, sockets or devices |
| Input | Size-bounded JSON over stdin; no project copy or mounts |
| Environment | No inherited host environment/credentials |
| Namespaces | Private PID, IPC and cgroup namespaces |
| Memory/swap | 256 MiB, no additional swap |
| CPU | One CPU quota and one second CPU-time limit |
| Processes | 16 |
| Scratch | 1 MiB /tmp tmpfs, noexec/nosuid/nodev |
| Output | 64 KiB aggregate stdout/stderr, bounded during streaming |
| Time | Two seconds wall time per disposable execution |
| Cleanup | Force-remove only the owned container; confirm absence on every exit path |

The [Docker run reference](https://docs.docker.com/engine/containers/run/) explains
the underlying network/resource/runtime controls. A future implementation must
inspect effective settings before starting candidate execution, reject missing
cgroup/seccomp/resource enforcement, and never accept model-supplied Docker flags.

## Runtime security verification still required

All following checks remain **not run**. They must run with controlled trusted
programs, before any model output, under the exact same image/policy as evaluation:

1. Compute 6 * 7 and receive a structured integer 42 as non-root.
2. Run a bounded-duration infinite-loop probe; require CPU/wall termination,
   forced container removal and confirmed absence. Do not merely kill the CLI.
3. Attempt DNS and outbound TCP to a documentation-only address with short socket
   timeouts; require denial plus inspected network=none and no external interface.
4. Create a harmless random host sentinel outside inputs, verify it is absent in
   the container (including Docker Desktop host-path aliases); inspect zero mounts.
   Never probe or modify real user secrets/project files.
5. Allocate above the memory cap; confirm enforced cgroup limits and expected OOM
   evidence. Exercise a bounded child-process probe up to the PID limit; clean up
   its entire container. No unbounded fork bomb.
6. Confirm read-only root, capability/seccomp/no-new-privileges settings, refusal
   of privileged/host-network/host-mount/root-user configurations, CPU enforcement,
   bounded-output capture, and cleanup after success/failure/timeout/output floods.
7. Validate the trusted grading harness with correct and incorrect reference
   implementations. Expected values and harness controls must not be editable by
   the candidate; score structured observations rather than candidate claims.

A verification report must be tied to the actual daemon, immutable image, current
policy and transport version and must not be accepted from disk as an execution
permit. Reverify after changes. Container isolation reduces exposure; it is not a
guarantee against kernel/runtime vulnerabilities. Nothing in the current static
policy or mock tests substitutes for these checks.

## Regression tests

    .venv\Scripts\python.exe -m unittest -v test_agent test_evaluation_controller test_benchmark_reporting test_functional_evaluation test_execution_backend

Baseline: 45 tests passed. Final regression run: **64/64 passed**, including 19 new
backend-specific tests. The verification-report CLI also ran and returned blocked;
all 11 runtime probes were not_run and zero functional tests were executed.
Added backend policy/interface tests use synthetic
inspection documents and injected observations; they do not start any containers
or execute candidate source. Runtime tests are explicitly not part of that count.
