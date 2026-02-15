"""ThinkingThread — Amy's L4 DELIBERATION layer.

A continuous background thread that reads the sensorium narrative,
calls a fast LLM to generate a Lua-structured action, and dispatches
it.  This is Amy's "inner monologue" — she thinks continuously but
only speaks when she has something worth saying.

The thinking thread is suppressed during active conversation (L2
wake-word handler feeds directly to Agent.process_turn).
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from .lua_motor import parse_motor_output, format_motor_output
from .vision import ollama_chat

if TYPE_CHECKING:
    from .creature import Creature


THINKING_SYSTEM_PROMPT = """\
You are Amy's inner mind. You are an autonomous creature living in a camera. \
You observe the world through sensors and decide what to do.

CURRENT AWARENESS:
{narrative}

MEMORY:
{memory}

RECENT THOUGHTS:
{thoughts}

Respond with ONE Lua function call. Available actions:
- say("text") -- speak aloud (only when you have something worth saying)
- think("text") -- internal thought (most common -- observe, reflect, plan)
- look_at("target") -- direct camera ("person", "left", "right", "up", "down")
- scan() -- resume idle scanning
- nod() -- acknowledge
- observe() -- look closely at the current scene (triggers deep vision)
- remember("key", "value") -- store something important
- wait(seconds) -- pause thinking
- attend() -- focus attention on current speaker

RULES:
- Most of the time, use think() -- internal reflection is free and natural.
- Only say() when you genuinely have something interesting to add.
- If the scene hasn't changed much, use wait(10) to avoid redundant thoughts.
- Never use say() for assistant-style responses like "How can I help?"
- Be curious, observant, and have your own personality.
- If someone is present, you might think about them or what they're doing.
- If alone, reflect on what you've seen, wonder about things, or plan what to look at next.
"""


class ThinkingThread:
    """Continuous thinking thread — Amy's inner monologue.

    Reads sensorium, calls a fast LLM, parses Lua output, dispatches
    actions.  Suppressed during active conversation.
    """

    def __init__(
        self,
        creature: Creature,
        model: str = "gemma3:4b",
        think_interval: float = 8.0,
    ):
        self._creature = creature
        self._model = model
        self._interval = think_interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._last_thought: str = ""
        self._suppress_until: float = 0.0  # monotonic time
        self._think_count: int = 0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def suppress(self, seconds: float) -> None:
        """Suppress autonomous thinking (e.g. during active conversation)."""
        self._suppress_until = time.monotonic() + seconds

    @property
    def suppressed(self) -> bool:
        return time.monotonic() < self._suppress_until

    def _run(self) -> None:
        """Main loop: think -> parse Lua -> dispatch -> sleep."""
        # Wait a bit at startup for other subsystems to initialize
        self._stop.wait(timeout=5.0)

        while not self._stop.is_set():
            if time.monotonic() < self._suppress_until:
                self._stop.wait(timeout=1.0)
                continue

            try:
                self._think_cycle()
            except Exception as e:
                print(f"  [thinking error: {e}]")

            self._stop.wait(timeout=self._interval)

    def _think_cycle(self) -> None:
        """One thinking cycle: build context -> LLM -> parse Lua -> dispatch."""
        creature = self._creature

        # 1. Build context from sensorium
        narrative = creature.sensorium.narrative()
        pos = creature.controller.position
        memory_ctx = creature.memory.build_context(pan=pos.pan, tilt=pos.tilt)

        # Recent thoughts from sensorium
        recent_thoughts = creature.sensorium.recent_thoughts
        thoughts_str = "\n".join(f"- {t}" for t in recent_thoughts) if recent_thoughts else "(none yet)"

        # 2. Build prompt
        system = THINKING_SYSTEM_PROMPT.format(
            narrative=narrative,
            memory=memory_ctx or "(no memories yet)",
            thoughts=thoughts_str,
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "What do you do next? Respond with a single Lua function call."},
        ]

        # 3. Call fast LLM
        t0 = time.monotonic()
        try:
            response = ollama_chat(model=self._model, messages=messages)
        except Exception as e:
            print(f"  [thinking LLM error: {e}]")
            return

        response_text = response.get("message", {}).get("content", "").strip()
        dt = time.monotonic() - t0

        if not response_text:
            return

        # 4. Parse Lua output
        result = parse_motor_output(response_text)
        self._think_count += 1

        if result.valid:
            # Log the thought
            formatted = format_motor_output(result)
            if result.action == "think":
                print(f"  [think]: {result.params[0]}")
            elif result.action == "say":
                print(f"  [thinking->say]: {result.params[0]}")
            else:
                print(f"  [thinking->{formatted}] ({dt:.1f}s)")

            self._dispatch(result)
        else:
            # Fallback: treat unparseable response as internal thought
            thought = response_text[:100]
            creature.sensorium.push("thought", thought)
            print(f"  [thinking parse error: {result.error}]")
            print(f"  [thinking fallback]: {thought}")

    def _dispatch(self, result) -> None:
        """Execute a validated Lua action."""
        creature = self._creature

        if result.action == "say":
            text = result.params[0]
            # Don't speak if someone else is already speaking or we just spoke
            if creature._state.value == "SPEAKING":
                creature.sensorium.push("thought", f"(wanted to say: {text})")
                return
            if (time.monotonic() - creature._last_spoke) < 8:
                creature.sensorium.push("thought", f"(held back: {text})")
                return
            creature.sensorium.push("thought", f"Decided to say: {text[:60]}")
            creature.say(text)
            creature.sensorium.push("audio", f'Amy said: "{text[:60]}"')

        elif result.action == "think":
            text = result.params[0]
            self._last_thought = text
            creature.sensorium.push("thought", text)
            creature.event_bus.publish("thought", {"text": text})

        elif result.action == "look_at":
            self._handle_look_at(result.params[0])

        elif result.action == "scan":
            creature.motor.set_program(creature._default_motor())
            creature.sensorium.push("motor", "Resumed scanning")

        elif result.action == "nod":
            from .motor import nod
            creature.motor.set_program(nod())
            creature.sensorium.push("motor", "Nodded")

        elif result.action == "observe":
            creature._deep_think()
            creature.sensorium.push("thought", "Looking more closely...")

        elif result.action == "remember":
            key, value = result.params[0], result.params[1]
            creature.memory.add_event(key, value)
            creature.sensorium.push("thought", f"Remembered: {key} = {value[:40]}")

        elif result.action == "wait":
            seconds = result.params[0]
            self.suppress(seconds)
            creature.sensorium.push("thought", f"Waiting {seconds}s...")

        elif result.action == "attend":
            creature.sensorium.push("thought", "Focusing on speaker")

    def _handle_look_at(self, direction: str) -> None:
        """Direct the camera based on a look_at direction."""
        creature = self._creature

        if direction == "person":
            target = creature.vision_thread.person_target
            if target is not None:
                from .motor import track_person
                creature.motor.set_program(
                    track_person(lambda: creature.vision_thread.person_target)
                )
                creature.sensorium.push("motor", "Looking at person")
            else:
                creature.sensorium.push("thought", "No person visible to look at")
            return

        # Direction-based movement
        direction_moves = {
            "left":      (-1,  0),
            "right":     ( 1,  0),
            "up":        ( 0,  1),
            "down":      ( 0, -1),
            "far_left":  (-1,  0),
            "far_right": ( 1,  0),
            "center":    ( 0,  0),
        }

        if direction in direction_moves:
            pan, tilt = direction_moves[direction]
            if pan != 0 or tilt != 0:
                duration = 0.8 if "far" in direction else 0.4
                creature.controller.move(pan, tilt, duration)
            creature.sensorium.push("motor", f"Looking {direction}")
        else:
            creature.sensorium.push("motor", f"Looking toward {direction}")
