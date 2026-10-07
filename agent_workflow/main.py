from __future__ import annotations

import argparse
import sys
import uuid

from langgraph.types import Command

from src.config import available_providers
from src.graph import build_graph
from src.llm import ProviderError
from src.state import initial_state


def print_update(node_name, update):
    if not isinstance(update, dict):
        return
    print(f"  > {node_name}")
    for event in update.get("events", []):
        print(f"      [{event['node']}] {event['msg']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-agent SE system (skeleton)")
    parser.add_argument("request", help="what you want the agent team to build")
    parser.add_argument("--fail-rounds", type=int, default=0,
                        help="simulate validation failing for the first N repair rounds")
    parser.add_argument("--final-review", action="store_true",
                        help="pause for a human final review before delivery")
    parser.add_argument("--thread-id", default=None,
                        help="resume an existing run by thread id")
    parser.add_argument("--auto-resume", action="append", default=[],
                        help="answer to feed at each HITL prompt (repeatable, for scripted runs)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true",
                      help="force stub workers (no API calls)")
    mode.add_argument("--live", action="store_true",
                      help="force real LLM calls (requires an API key)")
    parser.add_argument("--provider", choices=["nebius", "nvidia"], default=None,
                        help="route every worker through this provider")
    args = parser.parse_args()

    providers = available_providers()
    if args.live and not providers:
        print("error: --live needs NEBIUS_API_KEY or NVIDIA_API_KEY set")
        return 1
    mock = args.mock or (not args.live and not providers)

    thread_id = args.thread_id or str(uuid.uuid4())[:8]
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
    app = build_graph()

    mode_label = "MOCK (stub workers)" if mock else f"LIVE ({', '.join(providers)})"
    print(f"\nthread: {thread_id}   (reuse with --thread-id {thread_id})")
    print(f"mode: {mode_label}")
    if args.provider:
        print(f"forced provider: {args.provider}")
    print(f"request: {args.request}\n")

    payload = initial_state(
        args.request,
        fail_rounds=args.fail_rounds,
        final_review=args.final_review,
        mock=mock,
        force_provider=args.provider,
    )
    auto_iter = iter(args.auto_resume)

    try:
        final_state = run(app, payload, config, auto_iter, thread_id)
    except ProviderError as exc:
        print(f"\nprovider error: {exc}")
        return 1
    if final_state is None:
        return 2

    print("\n=== FINAL ===")
    print(f"status: {final_state.get('status')}")
    print(f"repair rounds used: {final_state.get('repair_round')}/"
          f"{final_state.get('max_repair_rounds')}")
    print(f"hitl answers: {[final_state.get('hitl', {}).get('answer')]}")
    output = final_state.get("final_output") or "(no output)"
    print("\n--- final_output ---")
    print(output)
    return 0


def run(app, payload, config, auto_iter, thread_id):
    for step in range(1, 31):
        print(f"--- step {step} ---")
        for batch in app.stream(payload, config, stream_mode="updates"):
            for node_name, update in batch.items():
                print_update(node_name, update)

        snapshot = app.get_state(config)
        if not snapshot.next:
            break

        interrupt_payload = {}
        for task in snapshot.tasks:
            if getattr(task, "interrupts", None):
                interrupt_payload = task.interrupts[0].value or {}
                break
        if not interrupt_payload:
            interrupts = snapshot.values.get("__interrupt__") or ()
            if interrupts:
                interrupt_payload = getattr(interrupts[0], "value", {}) or {}

        question = interrupt_payload.get("question", "Continue?")
        kind = interrupt_payload.get("kind", "clarification")
        print(f"\n[HITL:{kind}] {question}")

        try:
            answer = next(auto_iter)
            print(f"(auto-resume) {answer}")
        except StopIteration:
            try:
                answer = input("> ")
            except EOFError:
                print("stdin closed; stopping.")
                print(f"resume with: python main.py --thread-id {thread_id} \"...\"")
                return None

        payload = Command(resume=answer)

    return app.get_state(config).values


if __name__ == "__main__":
    sys.exit(main())