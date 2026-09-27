"""Run the legacy multi-process renderer with a finite wall-clock budget (POSIX)."""
import argparse
import os
import signal
import subprocess
import sys


def run(command, timeout):
    if os.name != 'posix':
        raise RuntimeError('Use Linux/WSL: process-group cleanup requires POSIX')
    if timeout <= 0 or not command:
        raise ValueError('positive timeout and command required')
    print(f'Render started; time limit {timeout:g}s. Worker output follows.', flush=True)
    process = subprocess.Popen(command, start_new_session=True)
    try:
        result = process.wait(timeout=timeout)
        if result:
            raise subprocess.CalledProcessError(result, command)
        return result
    finally:
        # Also terminate descendants left by an exited/crashed parent.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=3600)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    try:
        run(command, args.timeout)
    except (ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'Render failed; do not use partial output: {exc}', file=sys.stderr)
        sys.exit(1)
