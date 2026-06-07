#!/usr/bin/env python3
"""Pins coverage metadata in the shared evidence-bundle schema."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "..", "schemas", "evidence-bundle.schema.json")


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    with open(SCHEMA) as f:
        schema = json.load(f)

    props = schema["properties"]
    ok = True

    ok &= check("manifest schema: coverage_manifest present", "coverage_manifest" in props)
    ok &= check("manifest schema: source_reads present", "source_reads" in props)
    source_read = schema["$defs"]["source_read"]["properties"]
    ok &= check("manifest schema: status enum present",
                {"ok", "empty", "timeout", "error", "partial", "skipped"}.issubset(
                    set(source_read["status"]["enum"])
                ))
    ok &= check("manifest schema: source enum includes Slack MCP source",
                "slack" in source_read["source"]["enum"])

    email = props["email_coverage"]["properties"]
    ok &= check("email schema: searched_domains present", "searched_domains" in email)
    ok &= check("email schema: contact_domains present", "contact_domains" in email)
    ok &= check("email schema: newest_domain_thread_id present", "newest_domain_thread_id" in email)
    ok &= check("email schema: domain_thread_search_status present",
                "domain_thread_search_status" in email)

    internal = props["internal_evidence"]["properties"]
    ok &= check("slack schema: mcp checked present", "slack_mcp_checked" in internal)
    ok &= check("slack schema: channels searched present", "slack_channels_searched" in internal)
    room = internal["deal_room"]["properties"]
    ok &= check("slack schema: source is Slack only",
                room["source"]["enum"] == ["slack", None])
    ok &= check("slack schema: found coverage allowed",
                "found" in room["coverage"]["enum"])

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
