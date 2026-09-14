from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import TextIO

from seqchat.llm import ChatModel, HttpxChatCompletionsModel, ProviderError
from seqchat.readiness import check_database_readiness
from seqchat.settings import Settings

ModelFactory = Callable[[Settings], ChatModel]


def _default_model(settings: Settings) -> ChatModel:
    return HttpxChatCompletionsModel(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        json_mode=settings.llm_json_mode,
    )


def run_checks(
    settings: Settings,
    *,
    output: TextIO = sys.stdout,
    model_factory: ModelFactory = _default_model,
) -> int:
    """Run safe local and live-provider diagnostics in a fixed sequence."""
    configuration_error = settings.provider_configuration_error
    if configuration_error is not None:
        if configuration_error == "model_not_configured":
            names = ", ".join(settings.missing_provider_settings)
            print(f"[FAIL] Settings: missing {names}.", file=output)
        else:
            print("[FAIL] Settings: the provider base URL is invalid.", file=output)
        print("[SKIP] Database, endpoint, and structured-output checks.", file=output)
        return 1
    print("[PASS] Settings are present and valid.", file=output)

    database = check_database_readiness(settings.database_path)
    if database.status != "ready":
        print(f"[FAIL] Database: {database.message}", file=output)
        print("[SKIP] Endpoint and structured-output checks.", file=output)
        return 1
    print("[PASS] Database opens read-only and contains adsl.", file=output)

    try:
        model = model_factory(settings)
        model.generate_query(
            question="Return a read-only query that counts rows in adsl.",
            schema='adsl table:\n- "USUBJID" VARCHAR — Unique subject identifier',
        )
    except ProviderError as error:
        if error.upstream_reached:
            print("[PASS] Chat Completions endpoint returned an HTTP response.", file=output)
        else:
            print(f"[FAIL] Endpoint: {error.safe_message}.", file=output)
        print(
            f"[FAIL] Structured SQL output ({error.code}): {error.safe_message}.",
            file=output,
        )
        return 1
    except Exception:
        print("[FAIL] Endpoint: the diagnostic request failed safely.", file=output)
        print("[FAIL] Structured SQL output was not verified.", file=output)
        return 1

    print("[PASS] Chat Completions endpoint completed a request.", file=output)
    print("[PASS] Provider returned the required structured SQL shape.", file=output)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="seqchat-check",
        description=(
            "Check SeqChat settings, database, and provider compatibility. "
            "This makes a real model request and may incur provider cost."
        ),
    )
    parser.parse_args()
    raise SystemExit(run_checks(Settings()))


if __name__ == "__main__":
    main()
