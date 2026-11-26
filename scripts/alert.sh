#!/usr/bin/env bash
# Open, update or close the pipeline alert issue. GitHub emails the repository owner on every
# new issue and comment, so a failure reaches a person without any paid paging service.
#
#   scripts/alert.sh fail "<title>" "<details>"   # open the alert, or comment on the open one
#   scripts/alert.sh ok "<details>"               # close the open alert, saying what recovered
#
# Needs GH_TOKEN (the workflow's GITHUB_TOKEN with issues: write) and GITHUB_REPOSITORY.
set -euo pipefail
label=pipeline-alert
gh label create "$label" --color B60205 --description "The daily pipeline failed or is late" --force >/dev/null
open=$(gh issue list --label "$label" --state open --json number --jq '.[0].number // empty')
case "$1" in
  fail)
    if [ -n "$open" ]; then
      gh issue comment "$open" --body "$3"
    else
      gh issue create --label "$label" --title "$2" --body "$3"
    fi
    ;;
  ok)
    if [ -n "$open" ]; then
      gh issue close "$open" --comment "Recovered: $2"
    fi
    ;;
  *)
    echo "usage: $0 fail <title> <details> | ok <details>" >&2
    exit 2
    ;;
esac
