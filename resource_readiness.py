"""Small Windows resource observations and cooperative workload exclusion.

Readiness is not authorization, a reservation, or proof of sustained stability.
No process, model, pagefile or service is changed here.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
import threading
import time

from git_checkpoints import SafetyError

GIB = 1024 ** 3
LIMITS = {'generation': (4 * GIB, 10 * GIB), 'regression': (2 * GIB, 4 * GIB)}
_local = threading.Lock()
MUTEX_NAME = 'Local\\ALFHA-Serialized-Workloads-v1'


class Perf(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
        'CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal', 'PhysicalAvailable',
        'SystemCache', 'KernelTotal', 'KernelPaged', 'KernelNonpaged', 'PageSize')]
    _fields_ += [(name, wintypes.DWORD) for name in ('HandleCount', 'ProcessCount', 'ThreadCount')]


class ProcessEntry(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
               ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
               ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
               ('exe', wintypes.WCHAR * 260)]


def _kernel():
    if os.name != 'nt':
        raise OSError('Windows resource and workload evidence is required')
    dll = ctypes.WinDLL('kernel32', use_last_error=True)
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL
    return dll


def other_python_processes():
    """Conservative census: block other Python jobs, excluding this launcher chain."""
    dll = _kernel()
    dll.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    dll.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    dll.Process32FirstW.argtypes = dll.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    dll.Process32FirstW.restype = dll.Process32NextW.restype = wintypes.BOOL
    handle = dll.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError('Process inventory unavailable')
    rows = {}
    try:
        entry = ProcessEntry(); entry.size = ctypes.sizeof(entry)
        if not dll.Process32FirstW(handle, ctypes.byref(entry)):
            raise OSError('Incomplete process inventory')
        while True:
            rows[entry.pid] = {'pid': entry.pid, 'parent': entry.parent, 'name': entry.exe}
            if not dll.Process32NextW(handle, ctypes.byref(entry)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    raise OSError('Process inventory ended without complete evidence')
                break
    finally:
        dll.CloseHandle(handle)
    ancestors, pid = set(), os.getpid()
    while pid and pid not in ancestors:
        if pid not in rows:
            if pid == os.getpid():
                raise OSError('Current process inventory unavailable')
            break  # An exited ancestor is not an active competing workload.
        ancestors.add(pid)
        pid = rows[pid]['parent']
    return [r for pid, r in rows.items() if pid not in ancestors and
            (r['name'].lower().startswith(('python', 'pypy', 'pytest', 'alfha')))]


def memory_snapshot():
    if os.name != 'nt':
        raise OSError('Windows memory evidence unavailable')
    dll = ctypes.WinDLL('psapi', use_last_error=True)
    dll.GetPerformanceInfo.argtypes = [ctypes.POINTER(Perf), wintypes.DWORD]
    dll.GetPerformanceInfo.restype = wintypes.BOOL
    info = Perf()
    if not dll.GetPerformanceInfo(ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError('GetPerformanceInfo failed')
    return {'physical_total': info.PhysicalTotal * info.PageSize,
            'physical_available': info.PhysicalAvailable * info.PageSize,
            'commit_limit': info.CommitLimit * info.PageSize,
            'commit_used': info.CommitTotal * info.PageSize,
            'other_python_processes': other_python_processes()}


def check_readiness(kind='generation', *, sampler=None, pause=time.sleep):
    if kind not in LIMITS:
        raise ValueError('Unknown workload class')
    ram, commit = LIMITS[kind]
    report = {'ready': False, 'kind': kind, 'samples': [], 'errors': [],
              'minimum_available_ram': ram, 'minimum_commit_headroom': commit,
              'stability_guaranteed': False, 'read_only': True}
    for index in range(3):
        try:
            sample = (sampler or memory_snapshot)()
            if not isinstance(sample, dict):
                raise ValueError('Memory evidence must be an object')
            for key in ('physical_total', 'physical_available', 'commit_limit', 'commit_used'):
                if type(sample.get(key)) is not int or sample[key] < 0:
                    raise ValueError('Missing or invalid memory field: ' + key)
            if not (0 < sample['physical_total'] >= sample['physical_available'] and
                    0 < sample['commit_limit'] >= sample['commit_used']):
                raise ValueError('Inconsistent memory evidence')
            if not isinstance(sample.get('other_python_processes'), list):
                raise ValueError('Missing process inventory')
            sample = dict(sample, commit_headroom=sample['commit_limit'] - sample['commit_used'])
            report['samples'].append(sample)
            if sample['other_python_processes']:
                raise ValueError('Another Python/ALFHA job is active; finish it before starting this workload')
            if sample['physical_available'] < ram or sample['commit_headroom'] < commit:
                raise ValueError(f'Insufficient memory: require {ram // GIB} GiB available RAM and '
                                 f'{commit // GIB} GiB commit headroom. Wait for idle workloads or save '
                                 'and close optional applications; no settings or processes were changed')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            report['errors'].append(str(exc)); return report
        if index < 2:
            pause(0.2)
    report['ready'] = True
    return report


@contextmanager
def workload_guard(kind):
    """Nonblocking per-session Windows mutex; nested/competing work fails closed."""
    if not _local.acquire(blocking=False):
        raise SafetyError('An ALFHA workload is already active; serialize generation, Docker and regressions')
    dll, handle, owned = None, None, False
    try:
        dll = _kernel()
        dll.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        dll.CreateMutexW.restype = wintypes.HANDLE
        dll.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        dll.WaitForSingleObject.restype = wintypes.DWORD
        dll.ReleaseMutex.argtypes = [wintypes.HANDLE]
        dll.ReleaseMutex.restype = wintypes.BOOL
        handle = dll.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            raise SafetyError('Workload lock unavailable; no work authorized')
        state = dll.WaitForSingleObject(handle, 0)
        owned = state in (0, 0x80)
        if state != 0:
            raise SafetyError('Workload busy, abandoned, or unverifiable; review prior work before retrying')
        if other_python_processes():
            raise SafetyError('Another Python/ALFHA workload is active; finish it before starting ' + kind)
        yield
    finally:
        if owned: dll.ReleaseMutex(handle)
        if handle: dll.CloseHandle(handle)
        _local.release()
