"""Motor programs and motor thread for autonomous camera movement.

Motor programs are generators that yield MotorCommand dataclasses.
The MotorThread iterates the current program, executing commands via
the BCC950Controller.  Programs can be swapped at any time (e.g.
switching from idle_scan to breathe when speech is detected).
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Generator

from bcc950 import BCC950Controller

MotorProgram = Generator["MotorCommand", None, None]


@dataclass
class MotorCommand:
    """A single motor step for the motor thread to execute."""

    pan_dir: int = 0       # -1 left, 0 none, 1 right
    tilt_dir: int = 0      # -1 down, 0 none, 1 up
    duration: float = 0.1  # how long to move
    pause_after: float = 0.0  # how long to pause after the move


def idle_scan(controller: BCC950Controller) -> MotorProgram:
    """Smooth random scanning — the creature sweeping the room.

    Favors wide side-to-side sweeps to search for people and activity.
    Checks position limits before each step and reverses at edges.
    Includes pauses to "look at things."
    """
    pan = random.choice([-1, 1])
    tilt = 0
    while True:
        pos = controller.position

        # Pick a random movement pattern — biased toward wide panning
        roll = random.random()
        if roll < 0.50:
            # Wide pan sweep — the primary scanning motion
            if pan == -1 and not pos.can_pan_left:
                pan = 1
            elif pan == 1 and not pos.can_pan_right:
                pan = -1
            yield MotorCommand(
                pan_dir=pan,
                duration=random.uniform(0.3, 0.8),
                pause_after=random.uniform(0.2, 0.6),
            )
        elif roll < 0.75:
            # Pan + tilt diagonal sweep
            tilt = random.choice([-1, 1])
            if tilt == 1 and not pos.can_tilt_up:
                tilt = -1
            elif tilt == -1 and not pos.can_tilt_down:
                tilt = 1
            if pan == -1 and not pos.can_pan_left:
                pan = 1
            elif pan == 1 and not pos.can_pan_right:
                pan = -1
            yield MotorCommand(
                pan_dir=pan,
                tilt_dir=tilt,
                duration=random.uniform(0.2, 0.5),
                pause_after=random.uniform(0.3, 0.8),
            )
        elif roll < 0.88:
            # Pure tilt — glance up or down
            tilt = random.choice([-1, 1])
            if tilt == 1 and not pos.can_tilt_up:
                tilt = -1
            elif tilt == -1 and not pos.can_tilt_down:
                tilt = 1
            yield MotorCommand(
                tilt_dir=tilt,
                duration=random.uniform(0.1, 0.25),
                pause_after=random.uniform(0.3, 0.8),
            )
        else:
            # Pause — looking at something interesting
            yield MotorCommand(pause_after=random.uniform(1.0, 3.0))

        # Occasionally reverse pan direction
        if random.random() < 0.2:
            pan = -pan


def breathe() -> MotorProgram:
    """Imperceptible micro-tilt oscillations — keeps the creature 'alive'.

    Used during listening and thinking so the camera is never fully still.
    """
    while True:
        yield MotorCommand(tilt_dir=1, duration=0.05, pause_after=2.0)
        yield MotorCommand(tilt_dir=-1, duration=0.05, pause_after=2.0)


def nod() -> MotorProgram:
    """Small up-down nod for acknowledgment. Runs once then stops."""
    yield MotorCommand(tilt_dir=1, duration=0.12, pause_after=0.15)
    yield MotorCommand(tilt_dir=-1, duration=0.12, pause_after=0.15)
    yield MotorCommand(tilt_dir=1, duration=0.08, pause_after=0.1)
    yield MotorCommand(tilt_dir=-1, duration=0.08)


def search_scan(controller: BCC950Controller) -> MotorProgram:
    """Quick wide sweeps to find the source of a sound.

    Faster and more deliberate than idle_scan — covers more ground quickly
    when Amy hears something but can't see who's talking.
    """
    # Quick sweep: left, pause, right, pause, center
    for pan_dir in [-1, 1, -1, 1]:
        pos = controller.position
        if pan_dir == -1 and not pos.can_pan_left:
            pan_dir = 1
        elif pan_dir == 1 and not pos.can_pan_right:
            pan_dir = -1
        yield MotorCommand(pan_dir=pan_dir, duration=0.5, pause_after=0.4)
    # Then continue with wider sweeps
    pan = 1
    while True:
        pos = controller.position
        if pan == -1 and not pos.can_pan_left:
            pan = 1
        elif pan == 1 and not pos.can_pan_right:
            pan = -1
        yield MotorCommand(pan_dir=pan, duration=0.6, pause_after=0.3)
        pan = -pan


def track_person(target_fn) -> MotorProgram:
    """Track a person detected by YOLO — keeps camera centered on them.

    Args:
        target_fn: callable returning ``(cx_frac, cy_frac) | None``
            where fractions are in [0, 1] (0 = left/top, 1 = right/bottom).
    """
    while True:
        target = target_fn()
        if target is None:
            # No person visible — just breathe
            yield MotorCommand(tilt_dir=1, duration=0.05, pause_after=0.3)
            yield MotorCommand(tilt_dir=-1, duration=0.05, pause_after=0.3)
            continue

        cx, cy = target

        # Determine pan correction (dead zone in center 30-70%)
        pan = 0
        if cx < 0.35:
            pan = -1  # person is to the left
        elif cx > 0.65:
            pan = 1   # person is to the right

        # Determine tilt correction (dead zone 30-70%)
        tilt = 0
        if cy < 0.30:
            tilt = 1   # person is above center — tilt up
        elif cy > 0.70:
            tilt = -1  # person is below center — tilt down

        if pan != 0 or tilt != 0:
            # Proportional speed — further from center = longer move
            offset = max(abs(cx - 0.5), abs(cy - 0.5))
            duration = 0.05 + offset * 0.2
            yield MotorCommand(pan_dir=pan, tilt_dir=tilt, duration=duration, pause_after=0.15)
        else:
            # Person is centered — hold steady
            yield MotorCommand(pause_after=0.3)


def auto_track(controller: BCC950Controller, target_fn) -> MotorProgram:
    """Continuously track a person when visible, scan when not.

    This is Amy's default motor behavior — she's always either
    centered on someone or scanning the room looking for activity.

    Args:
        controller: BCC950Controller for position/limit checks.
        target_fn: callable returning ``(cx, cy) | None``.
    """
    pan_dir = random.choice([-1, 1])
    scan_hold = 0  # counter for "pause and look" during scanning

    while True:
        target = target_fn()

        if target is not None:
            # --- PERSON VISIBLE: center on them ---
            cx, cy = target
            pan = 0
            if cx < 0.35:
                pan = -1
            elif cx > 0.65:
                pan = 1
            tilt = 0
            if cy < 0.30:
                tilt = 1
            elif cy > 0.70:
                tilt = -1

            if pan != 0 or tilt != 0:
                offset = max(abs(cx - 0.5), abs(cy - 0.5))
                duration = 0.05 + offset * 0.15
                yield MotorCommand(pan_dir=pan, tilt_dir=tilt,
                                   duration=duration, pause_after=0.1)
            else:
                yield MotorCommand(pause_after=0.25)
        else:
            # --- NO PERSON: scan the room ---
            pos = controller.position
            if pan_dir == -1 and not pos.can_pan_left:
                pan_dir = 1
            elif pan_dir == 1 and not pos.can_pan_right:
                pan_dir = -1

            if scan_hold > 0:
                scan_hold -= 1
                yield MotorCommand(pause_after=0.5)
            else:
                yield MotorCommand(
                    pan_dir=pan_dir,
                    duration=random.uniform(0.3, 0.6),
                    pause_after=random.uniform(0.2, 0.4),
                )
                if random.random() < 0.15:
                    scan_hold = random.randint(2, 5)
                if random.random() < 0.2:
                    pan_dir = -pan_dir


class MotorThread:
    """Daemon thread that iterates a motor program, executing commands.

    The current program can be swapped with set_program().  The thread
    can be paused/resumed.  It sleeps in small increments so it can be
    interrupted quickly.
    """

    SLEEP_GRANULARITY = 0.05  # seconds — how often we check for interrupts

    def __init__(self, controller: BCC950Controller):
        self.controller = controller
        self._program: MotorProgram | None = None
        self._program_lock = threading.Lock()
        self._paused = threading.Event()
        self._paused.set()  # starts unpaused
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def set_program(self, program: MotorProgram | None) -> None:
        """Replace the current motor program. None means idle (do nothing)."""
        with self._program_lock:
            self._program = program

    def pause(self) -> None:
        """Pause motor execution (thread stays alive)."""
        self._paused.clear()

    def resume(self) -> None:
        """Resume motor execution."""
        self._paused.set()

    def stop(self) -> None:
        """Stop the motor thread permanently."""
        self._stop_event.set()
        self._paused.set()  # unblock if paused
        self._thread.join(timeout=3)

    def _interruptible_sleep(self, seconds: float) -> bool:
        """Sleep in small increments. Returns False if stop requested."""
        remaining = seconds
        while remaining > 0 and not self._stop_event.is_set():
            chunk = min(remaining, self.SLEEP_GRANULARITY)
            time.sleep(chunk)
            remaining -= chunk
        return not self._stop_event.is_set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            # Wait if paused
            self._paused.wait()
            if self._stop_event.is_set():
                break

            # Get next command from program
            with self._program_lock:
                program = self._program

            if program is None:
                if not self._interruptible_sleep(0.1):
                    break
                continue

            try:
                cmd = next(program)
            except StopIteration:
                with self._program_lock:
                    self._program = None
                continue

            # Execute the movement (if any)
            if cmd.pan_dir != 0 or cmd.tilt_dir != 0:
                # Check limits before executing
                pos = self.controller.position
                pan = cmd.pan_dir
                tilt = cmd.tilt_dir
                if pan == -1 and not pos.can_pan_left:
                    pan = 0
                if pan == 1 and not pos.can_pan_right:
                    pan = 0
                if tilt == -1 and not pos.can_tilt_down:
                    tilt = 0
                if tilt == 1 and not pos.can_tilt_up:
                    tilt = 0

                if pan != 0 or tilt != 0:
                    self.controller.move(pan, tilt, cmd.duration)
                elif cmd.duration > 0:
                    # Wanted to move but at limits — just wait
                    if not self._interruptible_sleep(cmd.duration):
                        break

            # Post-move pause
            if cmd.pause_after > 0:
                if not self._interruptible_sleep(cmd.pause_after):
                    break
